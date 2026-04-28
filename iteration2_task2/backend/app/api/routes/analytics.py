from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.task import ComparisonResponse
from app.services.evaluation_service import evaluation_service

router = APIRouter()


@router.get("/compare", response_model=ComparisonResponse)
def compare_tasks(
    task_ids: list[str] = Query(default=[]), db: Session = Depends(get_db)
) -> ComparisonResponse:
    return evaluation_service.compare(db, task_ids)
