from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import EvaluationResultORM
from app.schemas.task import EvaluationResult


class ResultRepository:
    def get(self, db: Session, task_id: str) -> EvaluationResult | None:
        row = db.get(EvaluationResultORM, task_id)
        return EvaluationResult.model_validate(row.payload) if row else None

    def upsert(self, db: Session, result: EvaluationResult) -> EvaluationResult:
        row = db.get(EvaluationResultORM, result.task_id)
        payload = result.model_dump(mode="json")

        if row is None:
            row = EvaluationResultORM(
                task_id=result.task_id,
                payload=payload,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        else:
            row.payload = payload
            row.updated_at = datetime.utcnow()

        db.add(row)
        db.commit()
        db.refresh(row)
        return EvaluationResult.model_validate(row.payload)


result_repository = ResultRepository()
