from fastapi import APIRouter, Query

from app.schemas.task import ComparisonResponse
from app.services.evaluation_service import evaluation_service

router = APIRouter()


@router.get("/compare", response_model=ComparisonResponse)
def compare_tasks(task_ids: list[str] = Query(default=[])) -> ComparisonResponse:
    return evaluation_service.compare(task_ids)
