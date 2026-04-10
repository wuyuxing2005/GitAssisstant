import argparse
import asyncio
import os
import signal
import sys
from  .agent_state import AgentState
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

    async def handle_command(self, cmd: str):
        parts = cmd.split()
        command = parts[0]

        # ===== 创建 / 切换 repo =====
        if command == "/repo" or command == "/switch":
            # 不论是新建还是切换，只需更新 SessionManager 里的指针
            repo = parts[1]
            self.manager.create_or_switch_session(repo)
            print(f"🔄 已切换到仓库工作区: {repo}")

        elif command == "/issue":
            # 针对当前工作区设定任务
            issue = " ".join(parts[1:])
            self.manager.set_issue(issue)
            print(f"📝 仓库 {self.manager.current_repo} 的 Issue 已设定。")

        elif command == "/run":
            # 1. 拿到当前的 thread_id
            thread_id = self.manager.get_current_thread_id()
            # 2. 把 thread_id 传给引擎，引擎会自动加载对应仓库的状态，并执行一步
            await self.orchestrator.run_step(thread_id)
            # 3. 打印执行后的状态
            state = self.manager.get_current_state()
            print(f"📊 [{self.manager.current_repo}] 当前状态: {state.get('status')}")

        elif command == "/help":
            print("""
            /repo <path>      进入仓库
            /switch <path>    a.k.a. /repo
            /issue <desc>     设置问题
            /run              单步执行
            /auto             自动执行
            /status           查看状态
            exit              退出
            """)

        else:
            print("⚠️ 未知命令")

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

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", "-m")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = args.model or os.getenv("MODEL_NAME", "hunyuan-lite")

    if not api_key:
        print("❌ 缺少 OPENAI_API_KEY")
        sys.exit(1)

    # ===== 初始化核心组件 =====
    model=LLM_factory()
    agent = Agent(model)
    orchestrator = AgentOrchestrator(agent)
    manager = SessionManager(orchestrator)

    cli = CLI(orchestrator, manager)

    asyncio.run(run_repl(cli))

if __name__ == "__main__":
    main()