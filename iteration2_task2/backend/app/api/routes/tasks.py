from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from app.db.database import get_db
from app.schemas.task import (
    EvaluationResult,
    EvaluationTaskCreate,
    EvaluationTaskResponse,
    EvaluationTaskUpdate,
)
from app.services.evaluation_service import evaluation_service
from app.services.task_service import task_service
from app.workers.evaluation_worker import run_evaluation_task

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
def run_task(
    task_id: str,
    db: Session = Depends(get_db),
    async_mode: Optional[bool] = False
) -> dict:
    """
    执行评测任务

    支持同步和异步两种模式：
    - 同步模式 (async_mode=False): 直接执行并返回评测结果
    - 异步模式 (async_mode=True): 提交到 Celery 队列并返回任务 ID
    """
    task = task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if async_mode:
        # 异步模式：提交到 Celery 队列
        task.status = "running"
        task_service.update_task(db, task_id, task)

        job = run_evaluation_task.delay(task_id)
        return {
            "status": "submitted",
            "task_id": task_id,
            "job_id": job.id,
            "message": "Task submitted to queue"
        }
    else:
        # 同步模式：直接执行
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


@router.get("/{task_id}/progress")
def get_task_progress(task_id: str, db: Session = Depends(get_db)) -> dict:
    """
    获取任务执行进度

    返回任务状态和执行进度信息。
    """
    task = task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 尝试从 Celery 获取进度（如果可用）
    try:
        from app.workers.celery_app import celery_app
        inspect = celery_app.control.inspect()
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}

        is_processing = False
        for worker_tasks in list(active.values()) + list(reserved.values()):
            for t in worker_tasks:
                if task_id in str(t.get("args", [])):
                    is_processing = True
                    break

        return {
            "task_id": task_id,
            "status": task.status,
            "is_processing": is_processing,
            "message": f"Task {task.status}"
        }
    except Exception:
        # Celery 不可用时返回基本状态
        return {
            "task_id": task_id,
            "status": task.status,
            "message": f"Task {task.status}"
        }
