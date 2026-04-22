from datetime import datetime

from app.models.task import EvaluationTaskRecord
from app.schemas.task import EvaluationConfig


class TaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[str, EvaluationTaskRecord] = {
            "eval-001": EvaluationTaskRecord(
                id="eval-001",
                name="客服 Agent 基线评测",
                description="验证基础问答效果、时延和安全性。",
                status="completed",
                config=EvaluationConfig(
                    agent_version="v1.3.0",
                    dataset="customer-support-v2",
                    evaluation_modes=["面向结果"],
                    evaluation_methods=["显式指标"],
                    dimensions=["效果", "安全", "性能"],
                    metrics=["answer_correctness", "latency", "safety"],
                    strategy="标准组合策略",
                ),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        }

    def list(self) -> list[EvaluationTaskRecord]:
        return list(self._tasks.values())

    def get(self, task_id: str) -> EvaluationTaskRecord | None:
        return self._tasks.get(task_id)

    def save(self, task: EvaluationTaskRecord) -> EvaluationTaskRecord:
        task.updated_at = datetime.utcnow()
        self._tasks[task.id] = task
        return task

    def delete(self, task_id: str) -> bool:
        return self._tasks.pop(task_id, None) is not None


task_repository = TaskRepository()
