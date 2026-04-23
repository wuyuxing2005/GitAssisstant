from fastapi import APIRouter, HTTPException

from app.schemas.task import (
    EvaluationResult,
    EvaluationTaskCreate,
    EvaluationTaskResponse,
    EvaluationTaskUpdate,
    TaskRunRequest,
)
from app.services.evaluation_service import evaluation_service
from app.services.task_service import task_service

router = APIRouter()


@router.get("/", response_model=list[EvaluationTaskResponse])
def list_tasks() -> list[EvaluationTaskResponse]:
    return task_service.list_tasks()


@router.post("/", response_model=EvaluationTaskResponse)
async def create_task(payload: EvaluationTaskCreate) -> EvaluationTaskResponse:
    task = task_service.create_task(payload)
    if payload.auto_start:
        try:
            record = await evaluation_service.run(
                task.id,
                TaskRunRequest(mode=task.config.run_mode, reset=True),
            )
            refreshed = task_service.get_task(record.id)
            if refreshed is not None:
                return refreshed
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task


@router.get("/{task_id}", response_model=EvaluationTaskResponse)
def get_task(task_id: str) -> EvaluationTaskResponse:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=EvaluationTaskResponse)
def update_task(task_id: str, payload: EvaluationTaskUpdate) -> EvaluationTaskResponse:
    task = task_service.update_task(task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if payload.config is not None:
        evaluation_service.clear_task_state(task_id)
    return task


@router.delete("/{task_id}")
def delete_task(task_id: str) -> dict[str, str]:
    evaluation_service.clear_task_state(task_id)
    deleted = task_service.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}


@router.post("/{task_id}/run", response_model=EvaluationTaskResponse)
async def run_task(
    task_id: str,
    payload: TaskRunRequest | None = None,
) -> EvaluationTaskResponse:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        updated_record = await evaluation_service.run(task_id, payload or TaskRunRequest())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    refreshed = task_service.get_task(updated_record.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return refreshed


@router.get("/{task_id}/results", response_model=EvaluationResult)
def get_task_result(task_id: str) -> EvaluationResult:
    result = evaluation_service.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result
