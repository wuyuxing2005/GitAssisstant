from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import TaskORM
from app.repositories.task_repository import task_repository
from app.schemas.task import (
    EvaluationTaskCreate,
    EvaluationTaskResponse,
    EvaluationTaskUpdate,
)


class TaskService:
    def list_tasks(self, db: Session) -> list[EvaluationTaskResponse]:
        return task_repository.list(db)

    def get_task(self, db: Session, task_id: str) -> EvaluationTaskResponse | None:
        return task_repository.get(db, task_id)

    def create_task(
        self, db: Session, payload: EvaluationTaskCreate
    ) -> EvaluationTaskResponse:
        now = datetime.utcnow()
        task = TaskORM(
            id=f"eval-{uuid4().hex[:8]}",
            name=payload.name,
            description=payload.description,
            status=payload.status,
            config=payload.config.model_dump(mode="json"),
            created_at=now,
            updated_at=now,
        )
        return task_repository.save(db, task)

    def update_task(
        self, db: Session, task_id: str, payload: EvaluationTaskUpdate
    ) -> EvaluationTaskResponse | None:
        task = task_repository.get_model(db, task_id)
        if task is None:
            return None

        if payload.name is not None:
            task.name = payload.name
        if payload.description is not None:
            task.description = payload.description
        if payload.status is not None:
            task.status = payload.status
        if payload.config is not None:
            task.config = payload.config.model_dump(mode="json")

        return task_repository.save(db, task)

    def delete_task(self, db: Session, task_id: str) -> bool:
        return task_repository.delete(db, task_id)


task_service = TaskService()
