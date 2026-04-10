# agent_state.py
from dataclasses import dataclass, field
from typing import TypedDict, Annotated, List, Dict, Any
from langchain_core.messages import BaseMessage
import operator


@dataclass
class AgentState(TypedDict):
    """Agent 状态，贯穿整个生命周期 (LangGraph 标准格式)"""
    repo_path: str
    issue_description: str
    
    # 核心状态
    status: str  # INIT, PLANNING, RUNNING, REFLECTING, SUCCESS, FAILED
    iteration_count: int
    max_iterations: int
    
    # 规划与反思
    plan: List[str]
    reflexion_notes: str
    
    # 消息流与轨迹 (使用 operator.add 让 LangGraph 自动合并列表而不是覆盖)
    messages: Annotated[List[BaseMessage], operator.add]
    trajectory: Annotated[List[Dict[str, Any]], operator.add]
