import argparse
import asyncio
import os
import shlex
import sys
from  .agent import Agent,LLM_factory
from  .orchestrator import AgentOrchestrator
from  .session_manager import SessionManager
from dotenv import load_dotenv

def _permission_mode(args: argparse.Namespace) -> str:
    return "default"
class CLI:
    def __init__(self, orchestrator:AgentOrchestrator, manager:SessionManager):
        self.orchestrator:AgentOrchestrator = orchestrator
        self.manager:SessionManager = manager
    
    def _print_status(self, state: dict):
        plan = state.get("plan") or []
        print(f"📊 状态: {state.get('status', 'UNKNOWN')}")
        print(f"📁 仓库: {state.get('repo_path', self.manager.current_repo or '未设置')}")
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

    async def _get_commit_plan_from_agent(self, state: dict, diff: str) -> dict | None:
            """让 Agent 根据修改内容和 issue 决定提交方案"""
            
            import json
            import re
            
            issue_description = state.get("issue_description", "")
            modified_files = self._extract_modified_files_from_diff(diff)
            
            prompt = f"""你是 Git 提交助手。根据以下信息，决定应该提交哪些文件以及撰写 commit message。

        ## 当前任务（Issue）
        {issue_description}

        ## 修改的文件列表
        {chr(10).join(f'- {f}' for f in modified_files)}

        ## 完整的修改内容（diff）
        {diff[:2000]}

        ## 请按照以下 JSON 格式输出（不要输出其他内容）：
        ```json
        {{
            "files": ["file1.py", "file2.py"],
            "message": "fix: 简要描述修复内容"
        }}
        ```
        ## 规则：
        只提交与修复直接相关的文件，排除自动生成的测试文件（除非 issue 要求添加测试）

        commit message 使用中文，格式：fix: 修复了XXX问题

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
                files.append(match.group(1))
        return files
    
    async def handle_command(self, cmd: str):
        parts = shlex.split(cmd)
        command = parts[0]

        try:
            # ===== 创建 / 切换 repo =====
            if command == "/repo" or command == "/switch":
                if len(parts) < 2:
                    print("用法: /repo <git_url|local_path> [target_dir]")
                    return
                repo_ref = parts[1]
                target_dir = parts[2] if len(parts) > 2 else None
                thread_id = self.manager.create_or_switch_session(repo_ref, target_dir)
                print(f"🔄 已切换到仓库工作区: {self.manager.current_repo}")
                print(f"🧵 当前线程: {thread_id}")

            elif command == "/issue":
                if len(parts) < 2:
                    print("用法: /issue <问题描述|issue编号|GitHub issue链接>")
                    return
                issue = " ".join(parts[1:])
                self.manager.set_issue(issue)
                print(f"📝 仓库 {self.manager.current_repo} 的 Issue 已设定。")

            elif command == "/run":
                thread_id = self.manager.get_current_thread_id()
                await self.orchestrator.run_step(thread_id)
                self._print_status(self.manager.get_current_state())

            elif command == "/solve":
                state = self.manager.get_current_state()
                if not state.get("issue_description"):
                    print("请先使用 /issue 设置问题。")
                    return
                thread_id = self.manager.get_current_thread_id()
                verbose = any(flag in parts[1:] for flag in ["--verbose", "-v"])
                final_state = await self.orchestrator.run_auto(thread_id, verbose=verbose)
                # 求解完成后，展示 diff 并询问是否推送
                if final_state.get("status") == "SUCCESS":
                    repo_path = final_state.get("repo_path")
                    from .tools.tools import _git_diff_impl, _git_push_impl, _git_add_impl, _git_commit_impl
                    
                    diff = _git_diff_impl(repo_path)
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
                            
                            confirm = input("\n🔐 是否按照 Agent 的建议提交并推送？(y/n): ")
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
                /repo <url|path> [dir]  下载或切换仓库
                /switch <url|path>      a.k.a. /repo
                /issue <desc|#number>   设置问题，支持 GitHub Issue 编号或链接
                /run                    单步执行
                /solve [-v|--verbose]   自动解决问题，verbose 输出更详细
                /status                 查看状态
                exit                    退出
                """)

            else:
                print("⚠️ 未知命令")
        except Exception as exc:
            print(f"❌ 命令执行失败: {exc}")

    async def handle_input(self, text):
        print("Warning：目前无任务, 默认测试API是否可用，请使用 /issue 设置任务或 /repo 创建任务")
        response=await self.orchestrator.raw_chat(text)
        print(response)


async def run_repl(cli:CLI):
    print("🚀 Agent CLI 启动！输入 /help 查看命令")

    while True:
        try:
            user_input = input("\n> ").strip()
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
    orchestrator = AgentOrchestrator(agent)
    manager = SessionManager(orchestrator, workspace_root=os.getcwd())

    cli = CLI(orchestrator, manager)

    asyncio.run(run_repl(cli))

if __name__ == "__main__":
    main()
