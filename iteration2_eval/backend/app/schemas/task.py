from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["draft", "scheduled", "running", "completed", "failed"]


class EvaluationConfig(BaseModel):
    agent_version: str = Field(..., description="待评测的 Agent 版本")
    dataset: str = Field(..., description="评测数据集标识")
    evaluation_modes: list[str] = Field(default_factory=list)
    evaluation_methods: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    strategy: str = Field(..., description="组合评估策略")


class EvaluationTaskBase(BaseModel):
    name: str
    description: str = ""
    config: EvaluationConfig


class EvaluationTaskCreate(EvaluationTaskBase):
    pass


class EvaluationTaskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    config: EvaluationConfig | None = None


class EvaluationTaskResponse(EvaluationTaskBase):
    id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime


class MetricScore(BaseModel):
    name: str
    value: float
    category: str


class EvaluationResult(BaseModel):
    task_id: str
    summary: str
    metrics: list[MetricScore]
    charts: list[str]
    logs_preview: list[str]


class ComparisonItem(BaseModel):
    task_id: str
    task_name: str
    scores: list[MetricScore]


class ComparisonResponse(BaseModel):
    compared_metrics: list[str]
    items: list[ComparisonItem]


class EvaluationMetadataResponse(BaseModel):
    modes: list[str]
    methods: list[str]
    dimensions: list[str]
    builtin_metrics: list[str]
    strategy_templates: list[str]
