# lite.py
from agent_state import AgentState
from reson import Reasoner
# 假设这是第二组提供的统一工具接口
from tool_interface import execute_tool, get_tools_description 

class AgentOrchestrator:
    def __init__(self, llm_client):
        self.reasoner = Reasoner(llm_client)
        
    def run(self, issue_desc: str, repo_path: str, yield_state=True):
        """
        主控流程。如果 yield_state=True，可作为生成器不断抛出状态，供第三组实时可视化。
        """
        state = AgentState(issue_description=issue_desc, repo_path=repo_path)
        state.status = "PLANNING"
        if yield_state: yield state

        # 1. Planning
        try:
            state.plan = self.reasoner.generate_plan(state)
            state.status = "RUNNING"
            if yield_state: yield state
        except Exception as e:
            state.status = "FAILED"
            state.reflexion_notes = f"Planning 失败: {str(e)}"
            if yield_state: yield state
            return state

        # 获取第二组的工具描述
        tools_desc = get_tools_description()

        # 2. Main ReAct Loop
        while state.iteration_count < state.max_iterations:
            state.iteration_count += 1
            
            # Step A: Reason & Act Decision
            action_req = self.reasoner.react_predict(state, tools_desc)
            
            # 终止条件判断：LLM 认为完成
            if action_req.tool_name.lower() in ["finish", "done", "complete"]:
                state.status = "SUCCESS"
                # TODO: 可以在这里调用第二组的生成 Patch 工具获取 final_patch
                if yield_state: yield state
                break

            # Step B: Execute (调用第二组的工具)
            # 第二组需要保证无论如何不能让程序崩溃，必须返回 ToolResult
            tool_result = execute_tool(action_req.tool_name, action_req.tool_input)

            # Step C: Observation & Record
            state.add_trajectory(
                thought=action_req.thought,
                action=action_req.tool_name,
                action_input=action_req.tool_input,
                observation=tool_result.observation
            )
            if yield_state: yield state

            # Step D: Reflexion (如果执行失败或测试未通过)
            if not tool_result.success:
                state.status = "REFLECTING"
                if yield_state: yield state
                
                # 更新反思笔记，供下一次 Loop 使用
                new_reflection = self.reasoner.reflect(state, tool_result.error_message or tool_result.observation)
                state.reflexion_notes += f"\n[迭代 {state.iteration_count} 经验]: {new_reflection}"
                
                state.status = "RUNNING"

        # 失败终止条件判断：超时
        if state.iteration_count >= state.max_iterations and state.status != "SUCCESS":
            state.status = "FAILED"
            state.reflexion_notes = "达到最大迭代次数，未能完成修复。"
        
        if yield_state: yield state
        return state