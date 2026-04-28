from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.task import (
    EvaluationResult,
    EvaluationTaskCreate,
    EvaluationTaskResponse,
    EvaluationTaskUpdate,
)
from app.services.evaluation_service import evaluation_service
from app.services.task_service import task_service

router = APIRouter()


@router.get("/", response_model=list[EvaluationTaskResponse])
def list_tasks(db: Session = Depends(get_db)) -> list[EvaluationTaskResponse]:
    return task_service.list_tasks(db)


@router.post("/", response_model=EvaluationTaskResponse)
def create_task(
    payload: EvaluationTaskCreate, db: Session = Depends(get_db)
) -> EvaluationTaskResponse:
    return task_service.create_task(db, payload)


@router.get("/{task_id}", response_model=EvaluationTaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)) -> EvaluationTaskResponse:
    task = task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=EvaluationTaskResponse)
def update_task(
    task_id: str, payload: EvaluationTaskUpdate, db: Session = Depends(get_db)
) -> EvaluationTaskResponse:
    task = task_service.update_task(db, task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    deleted = task_service.delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}


@router.post("/{task_id}/run", response_model=EvaluationResult)
def run_task(task_id: str, db: Session = Depends(get_db)) -> EvaluationResult:
    task = task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        return evaluation_service.run(db, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/results", response_model=EvaluationResult)
def get_task_result(task_id: str, db: Session = Depends(get_db)) -> EvaluationResult:
    result = evaluation_service.get_result(db, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result
