from app.models.task import EvaluationTaskRecord
from app.utils.time import now_local


class TaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[str, EvaluationTaskRecord] = {}

    def list(self) -> list[EvaluationTaskRecord]:
        return sorted(
            self._tasks.values(),
            key=lambda task: task.updated_at,
            reverse=True,
        )

    def get(self, task_id: str) -> EvaluationTaskRecord | None:
        return self._tasks.get(task_id)

    def save(self, task: EvaluationTaskRecord) -> EvaluationTaskRecord:
        task.updated_at = now_local()
        self._tasks[task.id] = task
        return task

    def delete(self, task_id: str) -> bool:
        return self._tasks.pop(task_id, None) is not None


task_repository = TaskRepository()
