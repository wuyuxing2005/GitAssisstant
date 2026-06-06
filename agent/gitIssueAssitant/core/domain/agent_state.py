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

    # 分层规划
    goals: List[Dict[str, Any]]
    current_goal_index: int
    plan_version: int
    replan_trigger: str  # "", "deviation", "goal_complete", "stuck"

    reflexion_notes: str

    # Skill 选择
    selected_skill: str  # "" 或 Skill 名称，如 "test-failure-fix"
    skill_instructions: str  # 选中 Skill 的正文，注入 react system prompt
    skill_priority_tools: List[str]
    skill_allowed_tools: List[str]

    # 消息流与轨迹
    messages: Annotated[List[BaseMessage], operator.add]
    trajectory: Annotated[List[Dict[str, Any]], operator.add]

    # 上下文压缩元数据
    compression_stats: Dict[str, Any]  # {"total_before": int, "total_after": int, "level2_summaries": int}

    # Token 用量累计
    token_usage: Dict[str, int]  # {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}

    # 沙箱标识（迭代三新增 — 第二组）
    sandbox_id: str  # thread_id，在 SandboxManager 中查找对应的 DockerSandbox 实例；空字符串表示未使用沙箱

    # 工具调用事件（迭代三新增 — 第二组，对应分工.md 3.2.6）
    # 每个元素是 ToolCallEvent.to_dict() 的结果，包含：
    # tool_name, arguments, status, result_preview, error_message, latency_ms, timestamp, sandbox_id, affected_files, exit_code
    # 第一组消费这些事件汇总 AgentTrace；第三组消费这些事件展示工具调用记录
    tool_call_events: Annotated[List[Dict[str, Any]], operator.add]

