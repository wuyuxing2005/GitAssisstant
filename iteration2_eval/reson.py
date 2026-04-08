# reson.py
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from agent_state import AgentState
from tool_interface import ActionRequest,ActionResponse
class Reasoner:
    def __init__(self, llm_client):
        self.llm = llm_client

    def generate_plan(self, state: AgentState) -> List[str]:
        """Planning 模块：根据 Issue 生成初始修复计划"""
        prompt = f"""
        你是一个资深程序员，请修复以下 GitHub Issue。
        Issue 描述: {state.issue_description}
        请将修复过程拆分为具体的步骤列表（例如：1. 定位文件 2. 搜索相关类 3. 修改代码 4. 运行测试）。
        请以 JSON 数组格式返回。
        """
        response = self.llm.chat(prompt)
        # 假设 LLM 返回 ["步骤1", "步骤2"]
        # 此处需加入 JSON 解析和容错逻辑
        return json.loads(response)

    def react_predict(self, state: AgentState, available_tools: str) -> ActionRequest:
        """ReAct 模块：根据当前状态和历史轨迹，决定下一步动作"""
        history_str = json.dumps(state.trajectory[-3:], ensure_ascii=False) # 取最近几次记录
        
        prompt = f"""
        请解决以下 Issue: {state.issue_description}
        当前执行计划步骤: {state.plan[state.current_step_index] if state.plan else '无'}
        你的反思笔记 (请务必参考): {state.reflexion_notes}
        最近的执行历史: {history_str}
        可用工具列表: {available_tools}
        
        请按照以下 JSON 格式输出你的决策：
        {{
            "thought": "你的思考过程",
            "tool_name": "选择的工具名（如果认为已修复完成，输出 'Finish'）",
            "tool_input": {{"参数名": "参数值"}}
        }}
        """
        response = self.llm.chat(prompt, response_format="json")
        result = json.loads(response)
        
        return ActionRequest(
            thought=result.get("thought", ""),
            tool_name=result.get("tool_name", ""),
            tool_input=result.get("tool_input", {})
        )

    def reflect(self, state: AgentState, failed_result: str) -> str:
        """Reflexion 模块：当测试失败或执行报错时进行反思"""
        prompt = f"""
        你在尝试修复 Issue 时遇到了失败。
        Issue: {state.issue_description}
        最近的动作历史: {json.dumps(state.trajectory[-2:])}
        失败信息/报错: {failed_result}
        
        请简短地分析失败原因，并给出一句话的改进策略，以指导后续操作。
        """
        reflexion = self.llm.chat(prompt)
        return reflexion