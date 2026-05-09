from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["draft", "scheduled", "running", "completed", "failed"]
EvaluationMode = Literal["result", "process"]
EvaluationMethod = Literal["explicit", "judge"]
EvaluationDimension = Literal["quality", "safety", "performance"]


class CustomMetricDefinition(BaseModel):
    key: str = Field(..., description="Unique metric key")
    label: str = Field(..., description="Display name")
    description: str = Field(default="", description="Metric description")
    dimension: EvaluationDimension = Field(..., description="Metric dimension")
    method: EvaluationMethod = Field(..., description="Metric scoring method")
    enabled: bool = Field(default=True, description="Whether the metric is enabled")
    judge_prompt: dict | None = Field(default=None, description="Judge 方法的自定义提示词配置")


class EvaluationStrategy(BaseModel):
    key: str = Field(..., description="Strategy identifier")
    label: str = Field(..., description="Strategy display name")
    description: str = Field(default="", description="Strategy summary")
    metric_keys: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)


class EvaluationConfig(BaseModel):
    dataset: str = Field(..., description="Dataset identifier")
    evaluation_modes: list[EvaluationMode] = Field(default_factory=list)
    evaluation_methods: list[EvaluationMethod] = Field(default_factory=list)
    dimensions: list[EvaluationDimension] = Field(default_factory=list)
    builtin_metrics: list[str] = Field(default_factory=list)
    custom_metrics: list[CustomMetricDefinition] = Field(default_factory=list)
    strategy: EvaluationStrategy


class EvaluationTaskBase(BaseModel):
    name: str
    description: str = ""
    config: EvaluationConfig


class EvaluationTaskCreate(EvaluationTaskBase):
    status: TaskStatus = "draft"


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
    key: str
    label: str
    value: float
    unit: str = "score"
    category: EvaluationDimension
    method: EvaluationMethod
    source: Literal["builtin", "custom"] = "builtin"
    description: str = ""


class EvaluationTimelineEvent(BaseModel):
    stage: str
    status: Literal["pending", "running", "completed"]
    message: str


class EvaluationResult(BaseModel):
    task_id: str
    task_name: str
    summary: str
    status: TaskStatus
    scorecard: dict[str, float]
    metrics: list[MetricScore]
    timeline: list[EvaluationTimelineEvent]
    charts: list[str]
    logs_preview: list[str]


class ComparisonItem(BaseModel):
    task_id: str
    task_name: str
    dataset: str
    status: TaskStatus
    scorecard: dict[str, float]
    scores: list[MetricScore]


class ComparisonResponse(BaseModel):
    compared_metrics: list[str]
    items: list[ComparisonItem]


class EvaluationMetadataResponse(BaseModel):
    modes: list[dict[str, str]]
    methods: list[dict[str, str]]
    dimensions: list[dict[str, str]]
    builtin_metrics: list[CustomMetricDefinition]
    strategy_templates: list[EvaluationStrategy]
    datasets: list[str]
