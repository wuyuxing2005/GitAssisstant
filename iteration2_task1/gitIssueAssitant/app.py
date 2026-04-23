#太不自由了，而且和CLI很重复，有空还是自己写一个前端吧！
import chainlit as cl
import shlex
from pathlib import Path

from dotenv import load_dotenv

from gitIssueAssitant.agent import Agent, LLM_factory
from gitIssueAssitant.orchestrator import AgentOrchestrator
from gitIssueAssitant.session_manager import SessionManager
from langchain_openai import ChatOpenAI # 根据你的实际导入

# ==========================================
# 1. 初始化会话 (对应你原来的 CLI 初始化)
# ==========================================
@cl.on_chat_start
async def on_chat_start():
    load_dotenv(Path(__file__).with_name(".env"), override=True)
    # 每次用户打开网页，初始化一套独立的 Manager 和 Orchestrator
    llm =LLM_factory() # 填入你的模型配置
    agent = Agent(llm=llm) # 你的 tools 如果是全局变量可以直接用
    orchestrator = AgentOrchestrator(agent=agent)
    manager = SessionManager(orchestrator, workspace_root=Path.cwd())

    # 将实例保存到 Chainlit 的当前用户会话中
    cl.user_session.set("orchestrator", orchestrator)
    cl.user_session.set("manager", manager)

    # 发送欢迎语
    await cl.Message(
        content="👋 欢迎使用智能代码修复助手！\n"
                "支持命令：\n"
                "`/repo <url|path>` - 设置仓库\n"
                "`/issue <desc>` - 设置任务\n"
                "`/solve` - 自动开始修复\n"
                "`/status` - 查看当前状态"
    ).send()

# ==========================================
# 2. 处理用户输入 (完美替代你的 CLI.handle_command)
# ==========================================
@cl.on_message
async def on_message(message: cl.Message):
    # 获取当前用户的实例
    orchestrator: AgentOrchestrator = cl.user_session.get("orchestrator")
    manager: SessionManager = cl.user_session.get("manager")
    
    text = message.content.strip()
    
    # --- 如果不是命令，走 Raw Chat 测试 ---
    if not text.startswith("/"):
        await cl.Message(content="*提示: 正在使用 Raw Chat 进行对话... (如需修复代码请使用 /repo 和 /issue 命令)*").send()
        response = await orchestrator.raw_chat(text)
        await cl.Message(content=response).send()
        return

    # --- 解析命令 ---
    parts = shlex.split(text)
    command = parts[0]

    try:
        if command in ["/repo", "/switch"]:
            if len(parts) < 2:
                await cl.Message(content="⚠️ 用法: `/repo <git_url|local_path>`").send()
                return
            repo_ref = parts[1]
            target_dir = parts[2] if len(parts) > 2 else None
            thread_id = manager.create_or_switch_session(repo_ref, target_dir)
            
            await cl.Message(
                content=f"✅ **已切换仓库**\n📁 路径: `{manager.current_repo}`\n🧵 线程: `{thread_id}`"
            ).send()

        elif command == "/issue":
            if len(parts) < 2:
                await cl.Message(content="⚠️ 用法: `/issue <问题描述>`").send()
                return
            issue = " ".join(parts[1:])
            manager.set_issue(issue)
            await cl.Message(content=f"📝 **Issue 已设定:**\n{issue}").send()

        elif command == "/status":
            state = manager.get_current_state()
            status_text = (
                f"**📊 状态:** {state.get('status', 'UNKNOWN')}\n"
                f"**📁 仓库:** {state.get('repo_path', manager.current_repo or '未设置')}\n"
                f"**📝 Issue:** {state.get('issue_description', '无')}\n"
                f"**🔁 迭代:** {state.get('iteration_count', 0)}"
            )
            await cl.Message(content=status_text).send()

        elif command == "/solve":
            state = manager.get_current_state()
            if not state.get("issue_description"):
                await cl.Message(content="⚠️ 请先使用 `/issue` 设置问题。").send()
                return
            
            thread_id = manager.get_current_thread_id()
            config = {"configurable": {"thread_id": thread_id}}
            
            await cl.Message(content="🚀 **开始自动求解...**").send()

            # ==========================================
            # 💡 核心改造：将你的 print 替换为 Chainlit 的折叠面板 (Steps)
            # ==========================================
            # 我们直接在此处遍历 graph.astream，而不是调用 orchestrator.run_auto
            # 这样可以在网页上实时展示每个节点的动画和输出
            async for event in orchestrator.graph.astream(None, config=config, stream_mode="updates"):
                for node_name, payload in event.items():
                    # 创建一个步骤 UI (类似 ChatGPT 的 "正在使用搜索工具...")
                    async with cl.Step(name=node_name) as step:
                        
                        # 针对不同节点定制显示内容
                        if node_name == "planner":
                            step.name = "🧭 规划修复步骤"
                            plan = payload.get("plan") or[]
                            if plan: step.output = plan[-1]
                        
                        elif node_name == "react":
                            step.name = f"🤖 Agent 思考 (第{payload.get('iteration_count', '?')}轮)"
                            msgs = payload.get("messages") or []
                            if msgs:
                                last_msg = msgs[-1]
                                content = getattr(last_msg, "content", "")
                                tool_calls = getattr(last_msg, "tool_calls",[])
                                output_text = content + "\n"
                                if tool_calls:
                                    output_text += f"\n🛠️ 准备调用工具: {', '.join([t['name'] for t in tool_calls])}"
                                step.output = output_text
                        
                        elif node_name == "tools":
                            step.name = "🛠️ 执行工具"
                            msgs = payload.get("messages") or[]
                            step.output = f"执行了 {len(msgs)} 个工具。\n"
                            for m in msgs:
                                step.output += f"**{getattr(m, 'name', 'tool')}** 结果:\n```\n{getattr(m, 'content', '')[:300]}...\n```\n"

                        elif node_name == "reflect":
                            step.name = "🪞 分析与反思"
                            step.output = payload.get("reflexion_notes", "")
                        
                        else:
                            step.name = f"⚙️ {node_name}"
                            step.output = str(payload)

            # 运行结束
            final_state = orchestrator.graph.get_state(config).values
            await cl.Message(content=f"🎉 **自动求解结束！最终状态: {final_state.get('status')}**").send()

        else:
            await cl.Message(content="⚠️ 未知命令，请查看支持的命令。").send()

    except Exception as exc:
        await cl.Message(content=f"❌ **执行失败:** {exc}").send()
