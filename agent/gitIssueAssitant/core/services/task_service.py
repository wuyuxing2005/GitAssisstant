from uuid import uuid4

from gitIssueAssitant.core.repositories.task_repository import task_repository
from gitIssueAssitant.core.schemas.task import (
    TaskCreate,
    TaskRecord,
    TaskResponse,
    TaskUpdate,
)
from gitIssueAssitant.core.utils.time import now_local


class TaskService:
    @staticmethod
    def _to_response(task: TaskRecord) -> TaskResponse:
        return TaskResponse(
            id=task.id,
            name=task.name,
            description=task.description,
            status=task.status,
            config=task.config,
            created_at=task.created_at,
            updated_at=task.updated_at,
            result=task.result,
        )

    def get_task_record(self, task_id: str) -> TaskRecord | None:
        return task_repository.get(task_id)

    def save_task_record(self, task: TaskRecord) -> TaskRecord:
        return task_repository.save(task)

    def list_tasks(self) -> list[TaskResponse]:
        return [self._to_response(task) for task in task_repository.list()]

    def get_task(self, task_id: str) -> TaskResponse | None:
        task = task_repository.get(task_id)
        return self._to_response(task) if task else None

    def create_task(self, payload: TaskCreate) -> TaskResponse:
        now = now_local()
        task = TaskRecord(
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
        self, task_id: str, payload: TaskUpdate
    ) -> TaskResponse | None:
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
            task.result = None
            task.thread_id = None
            task.repo_path = None
            task.started_at = None
            task.finished_at = None

        return self._to_response(task_repository.save(task))

    def delete_task(self, task_id: str) -> bool:
        return task_repository.delete(task_id)


task_service = TaskService()


