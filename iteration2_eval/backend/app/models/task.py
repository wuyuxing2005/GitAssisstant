from dataclasses import dataclass, field
from datetime import datetime

from app.schemas.task import EvaluationConfig, EvaluationResult, TaskStatus


@dataclass
class EvaluationTaskRecord:
    id: str
    name: str
    description: str
    status: TaskStatus
    config: EvaluationConfig
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    result: EvaluationResult | None = None
    thread_id: str | None = None
    repo_path: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
