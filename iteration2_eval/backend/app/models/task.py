from dataclasses import dataclass, field
from datetime import datetime

from app.schemas.task import EvaluationConfig, TaskStatus


@dataclass
class EvaluationTaskRecord:
    id: str
    name: str
    description: str
    status: TaskStatus
    config: EvaluationConfig
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
