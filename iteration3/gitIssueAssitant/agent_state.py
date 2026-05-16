# agent_state.py
from typing import TypedDict, Annotated, List, Dict, Any
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """Agent 状态，贯穿整个生命周期 (LangGraph 标准格式)"""
    repo_path: str
    issue_description: str

    # 核心状态
    status: str  # INIT, PLANNING, RUNNING, REFLECTING, REPLANNING, SUCCESS, FAILED
    iteration_count: int
    max_iterations: int

    # 分层规划
    goals: List[Dict[str, Any]]
    current_goal_index: int
    plan_version: int
    replan_trigger: str  # "", "deviation", "goal_complete", "stuck"

    reflexion_notes: str

    # 消息流与轨迹
    messages: Annotated[List[BaseMessage], operator.add]
    trajectory: Annotated[List[Dict[str, Any]], operator.add]

    # 上下文压缩元数据
    compression_stats: Dict[str, Any]  # {"total_before": int, "total_after": int, "level2_summaries": int}

    # Token 用量累计
    token_usage: Dict[str, int]  # {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
