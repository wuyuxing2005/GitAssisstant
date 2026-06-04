from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["draft", "scheduled", "running", "completed", "failed"]
RunMode = Literal["auto", "step"]
ExecutionOutcome = Literal["not_started", "running", "completed", "failed"]


class EvaluationConfig(BaseModel):
    repo_source: str = Field(..., description="本地仓库路径或 Git 仓库地址")
    issue_input: str = Field(..., description="Issue 描述、编号或 GitHub issue 链接")
    target_dir: str | None = Field(
        default=None,
        description="当 repo_source 为远程仓库时，本地克隆目录名",
    )
    model_name: str | None = Field(
        default=None,
        description="可选，覆盖默认的模型名称",
    )
    max_iterations: int = Field(default=15, ge=1, le=50)
    run_mode: RunMode = Field(default="auto")
    enabled_skills: list[str] | None = Field(
        default=None,
        description="本任务允许 Agent 路由使用的 Skill 名称列表；None 表示使用当前默认启用项。",
    )


class EvaluationTaskBase(BaseModel):
    name: str
    description: str = ""
    config: EvaluationConfig


class EvaluationTaskCreate(EvaluationTaskBase):
    auto_start: bool = False


class EvaluationTaskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    config: EvaluationConfig | None = None


class ToolCallRecord(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class TimelineEntry(BaseModel):
    id: str
    node: str
    event_type: str
    title: str
    content: str = ""
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    created_at: datetime


class ToolUsageItem(BaseModel):
    name: str
    count: int


MessageRole = Literal["user", "assistant", "system"]


class TaskMessage(BaseModel):
    id: str
    role: MessageRole
    content: str
    created_at: datetime
    replan: bool = False


class TaskMessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    replan: bool = False


class TaskMessageList(BaseModel):
    task_id: str
    messages: list[TaskMessage] = Field(default_factory=list)


class MetricScore(BaseModel):
    name: str
    value: float
    category: str
    unit: str | None = None
    description: str | None = None


class RuntimeSnapshot(BaseModel):
    thread_id: str | None = None
    repo_path: str | None = None
    sandbox_id: str = ""
    issue_description: str | None = None
    status: str = "INIT"
    iteration_count: int = 0
    max_iterations: int = 0
    plan: list[str] = Field(default_factory=list)
    reflexion_notes: str = ""
    last_message: str = ""


class FixReport(BaseModel):
    file_name: str
    markdown: str
    suggested_pr_title: str = ""
    suggested_pr_description: str = ""
    created_at: datetime


class EvaluationResult(BaseModel):
    task_id: str
    summary: str = ""
    outcome: ExecutionOutcome = "not_started"
    metrics: list[MetricScore] = Field(default_factory=list)
    logs_preview: list[str] = Field(default_factory=list)
    tool_usage: list[ToolUsageItem] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    messages: list[TaskMessage] = Field(default_factory=list)
    current_state: RuntimeSnapshot | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    fix_report: FixReport | None = None
    last_commit_hash: str | None = None
    pull_request_url: str | None = None


class EvaluationTaskResponse(EvaluationTaskBase):
    id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    result: EvaluationResult | None = None


class GitDiffResponse(BaseModel):
    task_id: str
    repo_path: str
    branch: str = ""
    status: str = ""
    diff: str = ""
    has_changes: bool = False


class GitPushRequest(BaseModel):
    commit_message: str | None = None
    remote: str = "origin"
    branch: str | None = None


class GitPushResponse(BaseModel):
    task_id: str
    repo_path: str
    commit_hash: str | None = None
    pushed: bool = False
    output: str = ""


class GitPullRequestRequest(BaseModel):
    commit_message: str | None = None
    title: str | None = None
    body: str | None = None
    remote: str = "origin"
    branch: str | None = None
    base_branch: str | None = None


class GitPullRequestResponse(BaseModel):
    task_id: str
    repo_path: str
    branch: str
    base_branch: str
    commit_hash: str | None = None
    pr_url: str | None = None
    output: str = ""


class GitHubIssueComment(BaseModel):
    id: int
    user: str = ""
    body: str = ""
    html_url: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GitHubIssueInfo(BaseModel):
    task_id: str
    owner: str
    repo: str
    number: int
    title: str = ""
    body: str = ""
    state: Literal["open", "closed"] | str = ""
    state_reason: str | None = None
    labels: list[str] = Field(default_factory=list)
    html_url: str = ""
    comments_count: int = 0
    comments: list[GitHubIssueComment] = Field(default_factory=list)
    default_comment: str = ""


class GitHubIssueCommentRequest(BaseModel):
    body: str = Field(..., min_length=1)


class GitHubIssueCommentResponse(BaseModel):
    id: int
    html_url: str = ""
    body: str = ""


class GitHubIssueStateRequest(BaseModel):
    state: Literal["open", "closed"]
    state_reason: Literal["completed", "not_planned"] | None = None


class GitHubIssueStateResponse(BaseModel):
    state: str
    state_reason: str | None = None
    html_url: str = ""


class GitHubIssueLabelsRequest(BaseModel):
    labels: list[str] = Field(default_factory=list)


class GitHubIssueLabelsResponse(BaseModel):
    labels: list[str] = Field(default_factory=list)


class ComparisonAggregate(BaseModel):
    success_rate: float = 0.0
    failed_count: int = 0
    average_duration_seconds: float = 0.0
    average_tool_call_count: float = 0.0
    average_test_run_count: float = 0.0


class ComparisonItem(BaseModel):
    task_id: str
    task_name: str
    status: TaskStatus
    summary: str = ""
    scores: list[MetricScore] = Field(default_factory=list)


class ComparisonResponse(BaseModel):
    compared_metrics: list[str]
    items: list[ComparisonItem]
    aggregate: ComparisonAggregate = Field(default_factory=ComparisonAggregate)


DEFAULT_BAD_CASE_TAGS = [
    "文件定位错误",
    "测试失败未恢复",
    "工具参数错误",
    "沙箱缺依赖",
    "过早判定成功",
    "上下文约束丢失",
    "环境/凭证问题",
]


class BadCaseBase(BaseModel):
    tags: list[str] = Field(default_factory=list)
    note: str = ""


class BadCaseCreate(BadCaseBase):
    task_id: str


class BadCaseUpdate(BadCaseBase):
    pass


class BadCaseRecord(BaseModel):
    id: str
    source_task_id: str
    task_name: str
    issue_input: str
    status: TaskStatus
    tags: list[str] = Field(default_factory=list)
    note: str = ""
    timeline: list[TimelineEntry] = Field(default_factory=list)
    metrics: list[MetricScore] = Field(default_factory=list)
    diff_summary: str = ""
    test_output_summary: str = ""
    summary: str = ""
    created_at: datetime
    updated_at: datetime


class BadCaseListResponse(BaseModel):
    items: list[BadCaseRecord] = Field(default_factory=list)
    default_tags: list[str] = Field(default_factory=lambda: list(DEFAULT_BAD_CASE_TAGS))


class BadCaseRerunRequest(BaseModel):
    name: str | None = None
    auto_start: bool = False


class SkillRecord(BaseModel):
    name: str
    description: str
    allowed_tools: list[str] = Field(default_factory=list)
    priority_tools: list[str] = Field(default_factory=list)
    body: str = ""
    enabled: bool = True


class SkillListResponse(BaseModel):
    items: list[SkillRecord] = Field(default_factory=list)


class SkillEnabledUpdate(BaseModel):
    enabled: bool


class ToolDescriptor(BaseModel):
    name: str
    category: str
    summary: str


class EvaluationMetadataResponse(BaseModel):
    modes: list[str]
    methods: list[str]
    dimensions: list[str]
    builtin_metrics: list[str]
    strategy_templates: list[str]
    builtin_tools: list[ToolDescriptor] = Field(default_factory=list)
    runtime_requirements: list[str] = Field(default_factory=list)


class TaskRunRequest(BaseModel):
    mode: RunMode | None = None
    reset: bool = False
    allow_local_fallback: bool = False
