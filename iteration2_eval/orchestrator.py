
from .agent_state import AgentState
from .agent import Agent
# 假设这是第二组提供的统一工具接口
from .tool_interface import execute_tool, get_tools_description 
# orchestrator.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.prebuilt import ToolNode
from .agent_state import AgentState
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

    # ============ 节点实现 ============
    async def _node_planner(self, state: AgentState):
        plan_text = await self.agent.generate_plan(state["issue_description"])
        return {"plan": [plan_text], "status": "PLANNING"}

    async def _node_react(self, state: AgentState):
        # 委托给 Agent 处理推理逻辑
        response = await self.agent.run_react(state["messages"])
        return {"messages": [response], "iteration_count": state["iteration_count"] + 1, "status": "RUNNING"}

    async def _node_reflect(self, state: AgentState):
        reflexion = await self.agent.reflect_on_failure(state["trajectory"])
        return {"reflexion_notes": reflexion, "status": "REFLECTING"}

    # ============ 路由控制逻辑 (Orchestrator 的核心职责) ============
    def _route_react(self, state: AgentState) -> str:
        last_msg = state["messages"][-1]
        
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
            
        # 如果什么都没做（比如 LLM 开始说废话），强制进入反思
        return "reflect"

    # ============ 外部调用接口 ============
    async def run_step(self, thread_id: str):
        """单步执行 (供 /run 使用)"""
        config = {"configurable": {"thread_id": thread_id}}
        # astream 会 yield 每个节点的执行结果
        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            return event # 每次只执行一个节点并返回

    async def run_auto(self, thread_id: str):
        """自动执行到底 (供 /auto 使用)"""
        config = {"configurable": {"thread_id": thread_id}}
        async for event in self.graph.astream(None, config=config, stream_mode="updates"):
            print(f"⚙️  Graph Step: {list(event.keys())[0]}")
    async def raw_chat(self,user_input):
        """
        This is for testing
        """
        return (await self.agent.chat(user_input)).content