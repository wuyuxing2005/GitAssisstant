import argparse
import asyncio
from contextlib import suppress
import os
import shlex
import sys
from  .agent import Agent,LLM_factory
from .cli_utils.commit import get_commit_plan_from_agent
from .cli_utils.git import run_git_capture, working_tree_diff_for_commit
from .cli_utils.reports import build_fix_report_markdown, write_fix_report
from .github_pr import create_github_pr
from  .orchestrator import AgentOrchestrator, MAX_ITERATIONS_REACHED_STATUS
from  .session_manager import SessionManager
from  .skills import SkillRegistry
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

def _permission_mode(args: argparse.Namespace) -> str:
    return "default"
class CLI:
    def __init__(self, orchestrator:AgentOrchestrator, manager:SessionManager):
        self.orchestrator:AgentOrchestrator = orchestrator
        self.manager:SessionManager = manager
        # /solve 自动运行期间，后台注入 reader 会把用户插话写入这里。
        self.input_queue: asyncio.Queue[str] = asyncio.Queue()
        self.solve_active: bool = False
        self.prompt_session: PromptSession | None = None
        self.injection_reader_task: asyncio.Task | None = None

    async def _read_line(self, prompt: str = "") -> str:
        """Read one interactive line through the shared PromptSession."""
        if self.prompt_session is None:
            raise RuntimeError("Prompt session has not been initialized.")
        return (await self.prompt_session.prompt_async(prompt)).strip()

    def _start_injection_reader(self):
        if self.prompt_session is None:
            raise RuntimeError("Prompt session has not been initialized.")
        if self.injection_reader_task is None or self.injection_reader_task.done():
            self.injection_reader_task = asyncio.create_task(
                _prompt_toolkit_reader(self, self.prompt_session)
            )

    async def _stop_injection_reader(self):
        if self.injection_reader_task is None:
            return
        self.injection_reader_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.injection_reader_task
        self.injection_reader_task = None

    async def _drain_injections(self, thread_id: str) -> int:
        """把队列中累积的用户输入注入到正在运行的 agent。返回本次注入的条数。

        以 !replan 开头的指令会同时设置 replan_trigger，让下一次反思路由回 h_planner。
        """
        count = 0
        while True:
            try:
                raw = self.input_queue.get_nowait()
            except asyncio.QueueEmpty:
                return count
            text = raw.strip()
            if not text:
                continue
            if text.startswith("!replan"):
                payload = text[len("!replan"):].strip() or "用户要求重新规划"
                self.orchestrator.inject_message(thread_id, payload, replan=True)
                print(f"📨 已注入并标记重规划: {payload}")
            else:
                self.orchestrator.inject_message(thread_id, text)
                print(f"📨 已注入用户输入: {text}")
            count += 1
    
    def _print_status(self, state: dict):
        plan = state.get("plan") or []
        session = self.manager._current_session()
        print(f"📊 状态: {state.get('status', 'UNKNOWN')}")
        print(f"📁 仓库: {state.get('repo_path', session.repo_path if session else '未设置')}")
        print(f"🔁 迭代次数: {state.get('iteration_count', 0)}/{state.get('max_iterations', 0)}")
        if state.get("issue_description"):
            print(f"📝 Issue: {state['issue_description']}")
        if plan:
            print("🗺️ 计划:")
            for idx, item in enumerate(plan, start=1):
                print(f"  {idx}. {item}")
        messages = state.get("messages") or []
        if messages:
            last_message = messages[-1]
            content = getattr(last_message, "content", "")
            if content:
                print(f"💬 最近输出: {content}")

    async def _ask_extend_iterations(self, state: dict) -> int | None:
        iteration_count = state.get("iteration_count", 0)
        max_iterations = state.get("max_iterations", 0)
        print(
            f"\n⏸️ Agent 已达到 max_iterations："
            f"{iteration_count}/{max_iterations}。"
        )
        print("是否延长对话继续？回车/yes 延长 5 轮；输入数字可自定义延长轮数；输入 n 结束。")
        answer = await self._read_line("[延长?] > ")
        while(True):
            normalized = answer.strip().lower()
            if normalized in ("", "y", "yes", "继续", "是"):
                return 5
            if normalized in ("n", "no", "否", "不", "停止", "结束"):
                return None
            if normalized.isdigit():
                return max(int(normalized), 1)
            print(f"⚠️ 未识别的输入: {answer}")
            answer = await self._read_line("[延长?] > ")

    async def handle_command(self, cmd: str):
        parts = shlex.split(cmd)
        command = parts[0]

        try:
            # ===== 创建会话 =====
            if command == "/repo" or command == "/new":
                if len(parts) < 2:
                    print("用法: /repo <git_url|local_path> [target_dir]")
                    return
                repo_ref = parts[1]
                target_dir = parts[2] if len(parts) > 2 else None
                force = "--force" in parts or "-f" in parts
                session, duplicates = self.manager.create_session(repo_ref, target_dir=target_dir, force=force)
                if duplicates and not force:
                    print(f"⚠️ 已存在 {len(duplicates)} 个相同仓库的会话:")
                    for s in duplicates:
                        print(f"   - [{s.session_id}] issue: {s.issue_ref or '未设置'} ({s.created_at})")
                    print("   如需强制创建，请加 --force 参数。已为你创建新会话。")
                print(f"🔄 已创建会话: {session.session_id}")
                print(f"📁 仓库: {session.repo_path}")
                print(f"🧵 线程: {session.thread_id}")

            # ===== 切换会话 =====
            elif command == "/switch":
                if len(parts) < 2:
                    print("用法: /switch <session_id>")
                    return
                session = self.manager.switch_session(parts[1])
                print(f"🔄 已切换到会话: {session.session_id}")
                print(f"📁 仓库: {session.repo_path}")
                print(f"📝 Issue: {session.issue_ref or '未设置'}")

            # ===== 列出会话 =====
            elif command == "/sessions":
                if len(parts) > 2:
                    print("用法: /sessions [session_id]")
                    return
                if len(parts) == 2:
                    session = self.manager.get_session(parts[1])
                    state = self.manager.get_session_state(parts[1])
                    marker = "是" if session.session_id == self.manager.current_session_id else "否"
                    print(f"会话: {session.session_id}")
                    print(f"线程: {session.thread_id}")
                    print(f"当前: {marker}")
                    print(f"仓库: {session.repo_path}")
                    print(f"Issue: {session.issue_ref or '未设置'}")
                    print(f"创建时间: {session.created_at}")
                    print(f"状态: {state.get('status', 'INIT')}")
                    print(
                        f"迭代: {state.get('iteration_count', 0)}/"
                        f"{state.get('max_iterations', session.max_iterations)}"
                    )
                    if session.issue_description:
                        print(f"Issue 描述: {session.issue_description}")
                else:
                    sessions = self.manager.list_sessions()
                    if not sessions:
                        print("暂无会话，使用 /repo 创建。")
                    else:
                        current_id = self.manager.current_session_id
                        for s in sessions:
                            marker = " ← 当前" if s.session_id == current_id else ""
                            print(f"  [{s.session_id}] repo={s.repo_path} issue={s.issue_ref or '未设置'}{marker}")

            elif command == "/issue":
                if len(parts) < 2:
                    print("用法: /issue <问题描述|issue编号|GitHub issue链接>")
                    return
                issue = " ".join(parts[1:])
                self.manager.set_issue(issue)
                session = self.manager._current_session()
                print(f"📝 会话 {session.session_id} 的 Issue 已设定。")

            elif command == "/run":
                thread_id = self.manager.get_current_thread_id()
                await self.orchestrator.run_step(thread_id)
                self._print_status(self.manager.get_current_state())

            elif command in ("/max_iterations", "/max-iterations", "/maxiter"):
                if len(parts) != 2 or not parts[1].isdigit():
                    print("用法: /max_iterations <正整数>，例如 /max_iterations 40")
                    return
                max_iterations = int(parts[1])
                state = self.manager.get_current_state()
                current_count = int(state.get("iteration_count") or 0)
                if current_count and max_iterations <= current_count:
                    print(
                        f"⚠️ 当前已执行 {current_count} 轮，"
                        f"请设置大于 {current_count} 的 max_iterations。"
                    )
                    return
                updated = self.manager.set_max_iterations(max_iterations)
                print(f"🔁 当前会话 max_iterations 已设置为 {updated}")

            elif command == "/solve":
                state = self.manager.get_current_state()
                if not state.get("issue_description"):
                    print("请先使用 /issue 设置问题。")
                    return
                thread_id = self.manager.get_current_thread_id()
                verbose = any(flag in parts[1:] for flag in ["--verbose", "-v"])

                print(
                    "💡 Agent 运行中可直接输入文字插入对话；"
                    "以 !replan 开头会同时触发重规划。"
                )
                self.solve_active = True
                try:
                    while True:
                        # 记录最后一次 drain 的注入数，用于判断终态时是否有「来不及处理」的输入
                        last_drain = 0
                        self._start_injection_reader()
                        try:
                            async for _step in self.orchestrator.run_auto_interactive(
                                thread_id, verbose=verbose
                            ):
                                last_drain = await self._drain_injections(thread_id)
                        finally:
                            await self._stop_injection_reader()

                        # generator 退出后再 drain 一次，捕获最后一个 yield 之后到达的输入
                        last_drain += await self._drain_injections(thread_id)

                        current_state = self.manager.get_current_state()
                        status = current_state.get("status", "")

                        if last_drain > 0:
                            # 视作「结束后的输入」：自动作为追加要求继续跑
                            print(
                                f"\n🔁 Agent 已结束 (status={status})，"
                                f"自动接续刚才的 {last_drain} 条追加输入..."
                            )
                            self.orchestrator.reopen_after_terminal(thread_id)
                            continue

                        if status == MAX_ITERATIONS_REACHED_STATUS:
                            extra_iterations = await self._ask_extend_iterations(current_state)
                            if extra_iterations is None:
                                self.orchestrator.mark_failed_after_user_declines_extension(thread_id)
                                print("🛑 已按用户选择结束，本次任务标记为 FAILED。")
                                break
                            self.orchestrator.reopen_after_terminal(
                                thread_id, extra_iterations=extra_iterations
                            )
                            print(f"🔁 已延长 {extra_iterations} 轮，继续运行。")
                            continue

                        if status not in ("SUCCESS", "FAILED"):
                            break

                        # Chat 模式：等用户继续输入；/done|done|exit|quit 才进入提交流程
                        print(
                            f"\n💬 Agent 已结束 (status={status})。"
                            f"继续输入会触发新一轮；输入 /done（或 done / exit / quit）进入提交流程。"
                        )
                        follow_up = await self._read_line("[还有问题吗] > ")
                        follow_up_norm = follow_up.strip().lower()
                        if follow_up_norm in ("", "/done", "done", "/exit", "exit", "/quit", "quit", "q"):
                            break

                        if follow_up.startswith("!replan"):
                            payload = follow_up[len("!replan"):].strip() or "用户要求重新规划"
                            self.orchestrator.inject_message(thread_id, payload, replan=True)
                            print(f"📨 已注入并标记重规划: {payload}")
                        else:
                            self.orchestrator.inject_message(thread_id, follow_up, replan=True)
                            print(f"📨 已注入追加要求并标记重规划: {follow_up}")
                        self.orchestrator.reopen_after_terminal(thread_id)
                finally:
                    self.solve_active = False
                    await self._stop_injection_reader()

                final_state = self.manager.get_current_state()
                # 求解完成后，展示 diff 并询问是否推送
                if final_state.get("status") == "SUCCESS":
                    repo_path = final_state.get("repo_path")
                    from .tools.tools import _git_push_impl, _git_add_impl, _git_commit_impl

                    diff = working_tree_diff_for_commit(repo_path)
                    if diff.strip():
                        print("\n" + "="*60)
                        print("📝 Agent 完成的修改内容：")
                        print("="*60)
                        print(diff)
                        print("="*60)

                        # 让 Agent 决定提交哪些文件和 commit message
                        print("🤖 Agent 正在决定提交方案...")

                        # 调用 Agent 生成提交计划
                        commit_plan = await get_commit_plan_from_agent(
                            self.orchestrator.agent.llm,
                            self.orchestrator.effective_issue_description(final_state),
                            diff,
                        )

                        report_markdown, pr_title, pr_body = build_fix_report_markdown(
                            final_state,
                            self.orchestrator.effective_issue_description(final_state),
                            diff,
                            commit_plan,
                        )
                        session = self.manager._current_session()
                        report_path = write_fix_report(
                            report_markdown,
                            session.session_id if session else None,
                        )
                        print(f"\n📝 已生成修复报告: {report_path}")

                        if commit_plan:
                            print(f"\n📦 Agent 建议提交的文件: {commit_plan['files']}")
                            print(f"📝 Agent 建议的提交信息: {commit_plan['message']}")

                            action = await self._read_line(
                                "\n请选择后续操作：1) 直接提交并推送  2) 提交并创建 PR  3) 什么都不做 > "
                            )
                            normalized_action = action.strip().lower()
                            if normalized_action in ("1", "commit", "push", "提交"):
                                add_result = _git_add_impl(commit_plan['files'])
                                print(f"📦 添加结果:\n{add_result}")
                                commit_result = _git_commit_impl(commit_plan['message'])
                                print(f"📝 提交结果:\n{commit_result}")
                                if "nothing to commit" not in commit_result.lower():
                                    print("🚀 正在推送...")
                                    push_result = _git_push_impl()
                                    print(push_result)
                                else:
                                    print("⏭️ 没有新提交，跳过推送")
                            elif normalized_action in ("2", "pr", "pull request", "提pr", "创建pr"):
                                base_branch = run_git_capture(
                                    repo_path,
                                    ["rev-parse", "--abbrev-ref", "HEAD"],
                                ).strip()
                                session = self.manager._current_session()
                                branch_name = f"agent-fix-{session.session_id if session else 'session'}"
                                checkout_result = run_git_capture(repo_path, ["checkout", "-B", branch_name])
                                print(f"🌿 分支结果:\n{checkout_result}")
                                add_result = _git_add_impl(commit_plan['files'])
                                print(f"📦 添加结果:\n{add_result}")
                                commit_result = _git_commit_impl(commit_plan['message'])
                                print(f"📝 提交结果:\n{commit_result}")
                                print("🚀 正在推送 PR 分支...")
                                push_result = run_git_capture(repo_path, ["push", "-u", "origin", branch_name])
                                print(push_result)
                                pr_url = create_github_pr(
                                    repo_path,
                                    branch_name,
                                    base_branch,
                                    pr_title,
                                    report_markdown or pr_body,
                                )
                                print(f"✅ PR 已创建: {pr_url}")
                            else:
                                print("⏭️ 已选择不提交、不创建 PR。")
                        else:
                            print("❌ Agent 无法生成提交计划，请手动处理")
                    else:
                        report_markdown, _, _ = build_fix_report_markdown(
                            final_state,
                            self.orchestrator.effective_issue_description(final_state),
                            diff,
                            None,
                        )
                        session = self.manager._current_session()
                        report_path = write_fix_report(
                            report_markdown,
                            session.session_id if session else None,
                        )
                        print(f"📝 没有检测到文件修改，已生成修复报告: {report_path}")
                print("✅ 自动求解结束。")
                self._print_status(final_state or self.manager.get_current_state())

            elif command == "/status":
                self._print_status(self.manager.get_current_state())

            elif command == "/help":
                print("""
                /repo <url|path> [dir] [-f]  创建新会话（关联仓库）
                /switch <session_id>         切换到已有会话
                /sessions [session_id]       列出所有会话，或查看指定会话详情
                /issue <desc|#number>        设置问题，支持 GitHub Issue 编号或链接
                /run                         单步执行
                /max_iterations <n>          设置当前会话最大推理轮数，默认25
                /solve [-v|--verbose]        自动解决问题（运行期间可随时插入对话）
                /status                      查看状态
                exit                         退出

                运行 /solve 时：
                  - 任意时刻直接输入文字 → 注入到下一节点的对话中
                  - 以 !replan <理由> 开头 → 同时触发重规划（回到 h_planner）
                  - Agent 到达终态后会进入 [solve+] chat 模式，继续输入会触发新一轮；
                    输入 /done 结束 chat 模式并进入提交流程
                """)

            else:
                print("⚠️ 未知命令")
        except Exception as exc:
            print(f"❌ 命令执行失败: {exc}")

    async def handle_input(self, text):
        print("Warning：目前无任务, 默认测试API是否可用，请使用 /issue 设置任务或 /repo 创建任务")
        response=await self.orchestrator.raw_chat(text)
        print(response)


async def _prompt_toolkit_reader(cli: CLI, session):
    while True:
        try:
            line = await session.prompt_async("\n[插入对话] > ")
        except (EOFError, KeyboardInterrupt):
            await cli.input_queue.put("exit")
            return
        await cli.input_queue.put(line.rstrip("\r\n"))


async def _repl_loop(cli: CLI):
    while True:
        try:
            user_input = await cli._read_line("\n> ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit"]:
            print("Bye.")
            break

        if user_input.startswith("/"):
            await cli.handle_command(user_input)
            continue

        await cli.handle_input(user_input)


async def run_repl(cli:CLI):
    print("Agent CLI started. Type /help for commands.")
    session = PromptSession()
    cli.prompt_session = session
    with patch_stdout():
        await _repl_loop(cli)


def main():
    load_dotenv()
    os.environ["GIT_ISSUE_ASSISTANT_HOME"] = os.getcwd()

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("❌ 缺少 OPENAI_API_KEY")
        sys.exit(1)

    # ===== 初始化核心组件 =====
    model=LLM_factory()
    agent = Agent(model)
    skill_registry = SkillRegistry()
    loaded_skills = skill_registry.load()
    if loaded_skills:
        print(f"🎯 已加载 {len(loaded_skills)} 个 Skill: {', '.join(loaded_skills.keys())}")
    orchestrator = AgentOrchestrator(agent, skill_registry=skill_registry)
    manager = SessionManager(orchestrator, workspace_root=os.getcwd())

    cli = CLI(orchestrator, manager)

    asyncio.run(run_repl(cli))

if __name__ == "__main__":
    main()
