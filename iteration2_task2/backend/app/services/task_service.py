from datetime import datetime
from uuid import uuid4

from app.models.task import EvaluationTaskRecord
from app.repositories.task_repository import task_repository
from app.schemas.task import (
    EvaluationTaskCreate,
    EvaluationTaskResponse,
    EvaluationTaskUpdate,
)


class TaskService:
    @staticmethod
    def _to_response(task: EvaluationTaskRecord) -> EvaluationTaskResponse:
        return EvaluationTaskResponse(
            id=task.id,
            name=task.name,
            description=task.description,
            status=task.status,
            config=task.config,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    def list_tasks(self) -> list[EvaluationTaskResponse]:
        return [self._to_response(task) for task in task_repository.list()]

    def get_task(self, task_id: str) -> EvaluationTaskResponse | None:
        task = task_repository.get(task_id)
        return self._to_response(task) if task else None

    def create_task(self, payload: EvaluationTaskCreate) -> EvaluationTaskResponse:
        now = datetime.utcnow()
        task = EvaluationTaskRecord(
            id=f"eval-{uuid4().hex[:8]}",
            name=payload.name,
            description=payload.description,
            status="draft",
            config=payload.config,
            created_at=now,
            updated_at=now,
        )
        return self._to_response(task_repository.save(task))

    def update_task(
        self, task_id: str, payload: EvaluationTaskUpdate
    ) -> EvaluationTaskResponse | None:
        task = task_repository.get(task_id)
        if task is None:
            return None

        if payload.name is not None:
            task.name = payload.name
        if payload.description is not None:
            task.description = payload.description
        if payload.status is not None:
            task.status = payload.status
        if payload.config is not None:
            task.config = payload.config

        return self._to_response(task_repository.save(task))

    def delete_task(self, task_id: str) -> bool:
        return task_repository.delete(task_id)


task_service = TaskService()
