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
