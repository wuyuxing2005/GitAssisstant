"""
Agent Trace 模型定义

用于记录 Agent 执行过程中的中间状态，支持过程导向评测。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TraceEventType(str, Enum):
    """Trace 事件类型"""

    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    LLM_GENERATION = "llm_generation"
    USER_INPUT = "user_input"
    SYSTEM_MESSAGE = "system_message"
    ERROR = "error"


class ToolCallInfo(BaseModel):
    """工具调用信息"""

    name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    result: Optional[Any] = Field(default=None, description="工具执行结果")
    status: str = Field(default="success", description="执行状态：success/error")
    latency_ms: float = Field(default=0.0, description="执行耗时 (毫秒)")


class TraceEvent(BaseModel):
    """单条 Trace 事件"""

    id: str = Field(..., description="事件 ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="时间戳")
    event_type: TraceEventType = Field(..., description="事件类型")
    message: Optional[str] = Field(default=None, description="事件消息内容")
    tool_call: Optional[ToolCallInfo] = Field(default=None, description="工具调用详情")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据")


class AgentTrace(BaseModel):
    """完整的 Agent 执行 Trace"""

    trace_id: str = Field(..., description="Trace ID")
    task_id: str = Field(..., description="关联的评测任务 ID")
    sample_id: str = Field(..., description="数据集中的样本 ID")
    user_input: str = Field(..., description="用户输入")
    final_response: str = Field(..., description="Agent 最终响应")
    events: list[TraceEvent] = Field(default_factory=list, description="事件列表")
    total_latency_ms: float = Field(default=0.0, description="总耗时 (毫秒)")
    token_usage: dict[str, int] = Field(
        default_factory=lambda: {"prompt": 0, "completion": 0, "total": 0},
        description="Token 使用情况",
    )


class TraceAnalysisResult(BaseModel):
    """Trace 分析结果"""

    sample_id: str
    tool_accuracy: float = Field(..., description="工具调用准确率")
    reasoning_quality: float = Field(..., description="推理质量评分")
    process_completeness: float = Field(..., description="流程完整性评分")
    issues: list[str] = Field(default_factory=list, description="发现的问题")
