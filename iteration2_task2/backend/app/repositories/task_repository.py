from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import TaskORM
from app.schemas.task import EvaluationConfig, EvaluationTaskResponse


def _to_response(task: TaskORM) -> EvaluationTaskResponse:
    return EvaluationTaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        status=task.status,
        config=EvaluationConfig.model_validate(task.config),
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


class TaskRepository:
    def list(self, db: Session) -> list[EvaluationTaskResponse]:
        tasks = db.query(TaskORM).order_by(TaskORM.updated_at.desc()).all()
        return [_to_response(task) for task in tasks]

    def get(self, db: Session, task_id: str) -> EvaluationTaskResponse | None:
        task = db.get(TaskORM, task_id)
        return _to_response(task) if task else None

    def get_model(self, db: Session, task_id: str) -> TaskORM | None:
        return db.get(TaskORM, task_id)

    def save(self, db: Session, task: TaskORM) -> EvaluationTaskResponse:
        task.updated_at = datetime.utcnow()
        db.add(task)
        db.commit()
        db.refresh(task)
        return _to_response(task)

    def delete(self, db: Session, task_id: str) -> bool:
        task = db.get(TaskORM, task_id)
        if task is None:
            return False
        db.delete(task)
        db.commit()
        return True


task_repository = TaskRepository()
