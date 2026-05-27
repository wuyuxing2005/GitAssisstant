import argparse
import asyncio
import os
from pathlib import Path
import shlex
import subprocess
import sys
from  .agent import Agent,LLM_factory
from  .orchestrator import AgentOrchestrator, MAX_ITERATIONS_REACHED_STATUS
from  .session_manager import SessionManager
from  .skills import SkillRegistry
from dotenv import load_dotenv

def _permission_mode(args: argparse.Namespace) -> str:
    return "default"
class CLI:
    def __init__(self, orchestrator:AgentOrchestrator, manager:SessionManager):
        self.orchestrator:AgentOrchestrator = orchestrator
        self.manager:SessionManager = manager
        # 后台 stdin reader 会把每行写入这里；REPL 与 /solve 都从此读取。
        self.input_queue: asyncio.Queue[str] = asyncio.Queue()
        self.solve_active: bool = False

    async def _read_line(self, prompt: str = "") -> str:
        """异步读取一行用户输入（来自后台 stdin reader）。"""
        if prompt:
            print(prompt, end="", flush=True)
        return (await self.input_queue.get()).strip()

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
        answer = await self._read_line("[extend?] > ")
        while(True):
            normalized = answer.strip().lower()
            if normalized in ("", "y", "yes", "继续", "是"):
                return 5
            if normalized in ("n", "no", "否", "不", "停止", "结束"):
                return None
            if normalized.isdigit():
                return max(int(normalized), 1)
            print(f"⚠️ 未识别的输入: {answer}")
            answer = await self._read_line("[extend?] > ")


    async def _get_commit_plan_from_agent(self, state: dict, diff: str) -> dict | None:
            """让 Agent 根据修改内容和 issue 决定提交方案"""
            
            import json
            import re
            
            issue_description = self.orchestrator.effective_issue_description(state)
            modified_files = self._extract_modified_files_from_diff(diff)
            
            prompt = f"""你是 Git 提交助手。根据以下信息，决定应该提交哪些文件以及撰写 commit message。

        ## 当前任务（Issue）
        {issue_description}

        ## 修改的文件列表
        {chr(10).join(f'- {f}' for f in modified_files)}

        ## 完整的修改内容（diff）
        {diff[:6000]}

        ## 请按照以下 JSON 格式输出（不要输出其他内容）：
        ```json
        {{
            "files": ["file1.py", "file2.py"],
            "message": "fix: 简要描述修复内容"
        }}
        ```
        ## 规则：
        只提交与当前任务和用户追加要求直接相关的文件。

        新增的源码文件和测试文件如果属于本次需求，也必须列入 files 数组。

        commit message 使用中文，格式：fix: 简要描述本次完整变更

        如果修改了多个文件，全部列入 files 数组

        不要添加 pycache、.pytest_cache 等临时文件"""
            try:
                response = await self.orchestrator.agent.llm.ainvoke(prompt)
                content = response.content.strip()
                json_match = re.search(r'json\s*(\{.*?\})\s*', content, re.DOTALL)
                if json_match:
                    plan = json.loads(json_match.group(1))
                else:
                    plan = json.loads(content)
                if "files" in plan and "message" in plan:
                    allowed_files = set(modified_files)
                    plan["files"] = [
                        file_path
                        for file_path in plan.get("files", [])
                        if file_path in allowed_files and not self._is_temporary_file(file_path)
                    ]
                    if not plan["files"]:
                        plan["files"] = [
                            file_path
                            for file_path in modified_files
                            if not self._is_temporary_file(file_path)
                        ]
                    return plan
                else:
                    print(f"❌ Agent 输出的提交方案格式不正确:{plan}")
                    return None
            except Exception as exc:
                print(f"❌ 解析 Agent 提交方案失败: {exc}")
                return None
    
    def _extract_modified_files_from_diff(self, diff: str) -> list[str]:
        """从 diff 输出中提取修改的文件列表"""
        import re
        files = []
        for line in diff.splitlines():
            if line.startswith("diff --git a/"):
                match = re.search(r'a/(.+?) b/', line)
                if match:
                    file_path = match.group(1)
                    if file_path not in files and not self._is_temporary_file(file_path):
                        files.append(file_path)
        return files

    def _is_temporary_file(self, file_path: str) -> bool:
        path = Path(file_path)
        ignored_parts = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        return any(part in ignored_parts for part in path.parts) or path.suffix == ".pyc"

    def _run_git_capture(self, repo_path: str, args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        return (result.stdout or "") + (result.stderr or "")

    def _untracked_file_diff(self, repo_path: str, relative_path: str) -> str:
        if self._is_temporary_file(relative_path):
            return ""
        full_path = Path(repo_path) / relative_path
        if not full_path.is_file():
            return ""
        data = full_path.read_bytes()
        if b"\0" in data:
            return ""
        text = data.decode("utf-8", errors="replace")
        lines = "".join(f"+{line}" for line in text.splitlines(keepends=True))
        if text and not text.endswith(("\n", "\r")):
            lines += "\n\\ No newline at end of file\n"
        return (
            f"diff --git a/{relative_path} b/{relative_path}\n"
            "new file mode 100644\n"
            "index 0000000..0000000\n"
            "--- /dev/null\n"
            f"+++ b/{relative_path}\n"
            "@@ -0,0 +1 @@\n"
            f"{lines}"
        )

    def _working_tree_diff_for_commit(self, repo_path: str) -> str:
        parts = [
            self._run_git_capture(repo_path, ["diff", "--no-ext-diff", "--binary"]),
            self._run_git_capture(repo_path, ["diff", "--no-ext-diff", "--binary", "--cached"]),
        ]
        status = self._run_git_capture(repo_path, ["status", "--porcelain", "--untracked-files=all"])
        for line in status.splitlines():
            if not line.startswith("?? "):
                continue
            relative_path = line[3:].strip().strip('"')
            untracked_diff = self._untracked_file_diff(repo_path, relative_path)
            if untracked_diff:
                parts.append(untracked_diff)
        return "\n".join(part for part in parts if part.strip())
    
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
                        async for _step in self.orchestrator.run_auto_interactive(
                            thread_id, verbose=verbose
                        ):
                            last_drain = await self._drain_injections(thread_id)

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
                        follow_up = await self._read_line("[solve+] > ")
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

                final_state = self.manager.get_current_state()
                # 求解完成后，展示 diff 并询问是否推送
                if final_state.get("status") == "SUCCESS":
                    repo_path = final_state.get("repo_path")
                    from .tools.tools import _git_push_impl, _git_add_impl, _git_commit_impl

                    diff = self._working_tree_diff_for_commit(repo_path)
                    if diff.strip():
                        print("\n" + "="*60)
                        print("📝 Agent 完成的修改内容：")
                        print("="*60)
                        print(diff)
                        print("="*60)

                        # 让 Agent 决定提交哪些文件和 commit message
                        print("🤖 Agent 正在决定提交方案...")

                        # 调用 Agent 生成提交计划
                        commit_plan = await self._get_commit_plan_from_agent(
                            final_state,
                            diff
                        )

                        if commit_plan:
                            print(f"\n📦 Agent 建议提交的文件: {commit_plan['files']}")
                            print(f"📝 Agent 建议的提交信息: {commit_plan['message']}")

                            confirm = await self._read_line("\n🔐 是否按照 Agent 的建议提交并推送？(y/n): ")
                            if confirm.lower() == 'y':
                                # 1. 添加文件
                                add_result = _git_add_impl(commit_plan['files'])
                                print(f"📦 添加结果:\n{add_result}")
                                
                                # 2. 提交
                                commit_result = _git_commit_impl(commit_plan['message'])
                                print(f"📝 提交结果:\n{commit_result}")
                                
                                # 3. 推送
                                if "nothing to commit" not in commit_result.lower():
                                    print("🚀 正在推送...")
                                    push_result = _git_push_impl()
                                    print(push_result)
                                else:
                                    print("⏭️ 没有新提交，跳过推送")
                            else:
                                print("⏭️ 已跳过提交和推送")
                        else:
                            print("❌ Agent 无法生成提交计划，请手动处理")
                    else:
                        print("📝 没有检测到文件修改")
                print("✅ 自动求解结束。")
                self._print_status(final_state or self.manager.get_current_state())

            elif command == "/status":
                self._print_status(self.manager.get_current_state())

            elif command == "/help":
                print("""
                /repo <url|path> [dir] [-f]  创建新会话（关联仓库）
                /switch <session_id>         切换到已有会话
                /sessions                    列出所有会话
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


async def _stdin_reader(cli: CLI):
    """后台从 stdin 持续读行并写入队列。

    使用 asyncio.to_thread 避免阻塞事件循环。线程在进程退出时随之结束。
    """
    while True:
        try:
            line = await asyncio.to_thread(sys.stdin.readline)
        except Exception:
            return
        if not line:
            # stdin 关闭
            return
        await cli.input_queue.put(line.rstrip("\r\n"))


async def run_repl(cli:CLI):
    print("🚀 Agent CLI 启动！输入 /help 查看命令")
    #启动异步读取
    reader_task = asyncio.create_task(_stdin_reader(cli))
    
    try:
        while True:
            # 注意：/solve 运行期间，用户输入会被 _drain_injections 抢走；
            # 这里只在没有 /solve 时拿到普通命令。
            print("\n> ", end="", flush=True)
            try:
                user_input = (await cli.input_queue.get()).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 拜拜！")
                break

            if not user_input:
                continue

            # ===== 退出 =====
            if user_input.lower() in ["exit", "quit"]:
                print("👋 拜拜！")
                break

            # ===== 命令 =====
            if user_input.startswith("/"):
                await cli.handle_command(user_input)
                continue

            # ===== 测试输入 =====
            await cli.handle_input(user_input)
    finally:
        reader_task.cancel()


def main():
    load_dotenv()
    os.environ["GIT_ISSUE_ASSISTANT_HOME"] = os.getcwd()

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", "-m")
    args = parser.parse_args()

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
