
from langchain_core.messages import HumanMessage

from .agent_state import AgentState
from .agent import Agent
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from .tools.tools import AGENT_TOOLS

class AgentOrchestrator:
    def __init__(self, agent: Agent, tools: list=AGENT_TOOLS):
        self.agent = agent
        self.tools = tools
        self.memory = MemorySaver()
        self.graph = self._build_graph()


    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # 1. 注册节点 (Nodes)
        workflow.add_node("planner", self._node_planner)
        workflow.add_node("react", self._node_react)
        workflow.add_node("tools", ToolNode(self.tools)) # 官方提供的工具执行节点
        workflow.add_node("reflect", self._node_reflect)

        # 2. 定义边和路由 (Edges & Routing)
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "react")
        
        workflow.add_conditional_edges(
            "react",
            self._route_react,
            {
                "continue_tools": "tools",
                "reflect": "reflect",
                "end_success": END,
                "end_failed": END
            }
        )
        
        workflow.add_edge("tools", "react")
        workflow.add_edge("reflect", "react")

        return workflow.compile(checkpointer=self.memory)

    def _shorten(self, text: str, limit: int = 300) -> str:
        text = (text or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    def _print_event(self, node_name: str, payload: dict, verbose: bool = False):
        if node_name == "planner":
            plan = payload.get("plan") or []
            print("🧭 正在规划修复步骤")
            if plan:
                print(f"   计划: {self._shorten(plan[-1], 500 if verbose else 180)}")
            return

        if node_name == "react":
            messages = payload.get("messages") or []
            if not messages:
                print("🤖 Agent 完成一轮思考")
                return

            ai_msg = messages[-1]
            content = getattr(ai_msg, "content", "") or ""
            tool_calls = getattr(ai_msg, "tool_calls", []) or []
            print(f"🤖 Agent 思考完成（第 {payload.get('iteration_count', '?')} 轮）")
            if content:
                print(f"   回复: {self._shorten(content, 800 if verbose else 220)}")
            if tool_calls:
                print(f"   工具调用数: {len(tool_calls)}")
                if verbose:
                    for idx, call in enumerate(tool_calls, start=1):
                        name = call.get("name", "unknown_tool")
                        args = call.get("args", {})
                        print(f"   [{idx}] {name} args={args}")
            return

        if node_name == "tools":
            messages = payload.get("messages") or []
            print(f"🛠️ 工具执行完成（{len(messages)} 条结果）")
            if verbose:
                for idx, message in enumerate(messages, start=1):
                    name = getattr(message, "name", None) or getattr(message, "tool_call_id", None) or f"tool_{idx}"
                    content = getattr(message, "content", "")
                    print(f"   [{idx}] {name}: {self._shorten(str(content), 800)}")
            return

        if node_name == "reflect":
            reflexion = payload.get("reflexion_notes", "")
            print("🪞 进入反思阶段")
            if reflexion:
                print(f"   反思: {self._shorten(reflexion, 800 if verbose else 220)}")
            return

        print(f"⚙️ Graph Step: {node_name}")

    # ============ 节点实现 ============
    async def _node_planner(self, state: AgentState):
        plan_text = await self.agent.generate_plan(state["issue_description"])
        return {
            "plan": [plan_text],
            "trajectory": [{"type": "plan", "content": plan_text}],
            "status": "PLANNING",
        }

    async def _node_react(self, state: AgentState):
        # 委托给 Agent 处理推理逻辑
        response = await self.agent.run_react(
            state["messages"],
            issue_description=state["issue_description"],
            repo_path=state.get("repo_path", ""),
            plan=state.get("plan", []),
            reflexion_notes=state.get("reflexion_notes", ""),
        )
        return {
            "messages": [response],
            "trajectory": [{"type": "ai", "content": response.content, "tool_calls": getattr(response, "tool_calls", [])}],
            "iteration_count": state["iteration_count"] + 1,
            "status": "RUNNING",
        }

    async def _node_reflect(self, state: AgentState):
        reflexion = await self.agent.reflect_on_failure(state["trajectory"])
        return {
            "messages": [HumanMessage(content=f"请根据这条反思调整后续策略：{reflexion}")],
            "reflexion_notes": reflexion,
            "trajectory": [{"type": "reflection", "content": reflexion}],
            "status": "REFLECTING",
        }

    # ============ 路由控制逻辑 (Orchestrator 的核心职责) ============
    def _route_react(self, state: AgentState) -> str:
        last_msg = state["messages"][-1]
        trajectory = state.get("trajectory", [])
        
        # 1. 检查是否超时/超次数
        if state["iteration_count"] >= state.get("max_iterations", 15):
            return "end_failed"
            
        # 2. 检查 LLM 是否决定调用工具 (重要！)
        if hasattr(last_msg, "tool_calls") and len(last_msg.tool_calls) > 0:
            return "continue_tools"
            
        # 3. 检查任务是否成功或失败
        content = last_msg.content or ""
        if "TASK_SUCCESS" in content:
            state["status"] = "SUCCESS"
            return "end_success"
        if "TASK_FAILED" in content:
            state["status"] = "FAILED"
            return "end_failed"

        previous_ai_contents = [
            item.get("content", "")
            for item in trajectory[:-1]
            if item.get("type") == "ai"
        ]
        if previous_ai_contents and content and content.strip() == previous_ai_contents[-1].strip():
            state["status"] = "FAILED"
            return "end_failed"

        recently_reflected = len(trajectory) >= 2 and trajectory[-2].get("type") == "reflection"
        if recently_reflected:
            state["status"] = "FAILED"
            return "end_failed"

        # 如果什么都没做（比如 LLM 开始说废话），只允许进入一次反思
        return "reflect"

    # ============ 外部调用接口 ============
    async def run_step(self, thread_id: str):
        """单步执行 (供 /run 使用)"""
        config = {"configurable": {"thread_id": thread_id}}
        # astream 会 yield 每个节点的执行结果
        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            return event # 每次只执行一个节点并返回

    async def run_auto(self, thread_id: str, verbose: bool = False):
        """自动执行到底 (供 /auto 使用)"""
        config = {"configurable": {"thread_id": thread_id}}
        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            node_name = list(event.keys())[0]
            self._print_event(node_name, event[node_name], verbose=verbose)
        return self.graph.get_state(config).values
    async def raw_chat(self,user_input):
        """
        This is for testing
        """
        return (await self.agent.chat(user_input)).content
