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
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.put("/{task_id}", response_model=EvaluationTaskResponse)
def update_task(
    task_id: str, payload: EvaluationTaskUpdate, db: Session = Depends(get_db)
) -> EvaluationTaskResponse:
    task = task_service.update_task(db, task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.delete("/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    deleted = task_service.delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "任务已删除"}


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
        raise HTTPException(status_code=404, detail="任务不存在")

    if async_mode:
        # 异步模式：提交到 Celery 队列
        task.status = "running"
        task_service.update_task(db, task_id, task)

        job = run_evaluation_task.delay(task_id)
        return {
            "status": "submitted",
            "task_id": task_id,
            "job_id": job.id,
            "message": "任务已提交到队列"
        }
    else:
        # 同步模式：直接执行
        try:
            return evaluation_service.run(db, task_id)
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail="评测数据集解码失败，请确认数据集文件保存为 UTF-8 编码。",
            ) from exc
        except ValueError as exc:
            if str(exc) in {"Task not found", "任务不存在"}:
                raise HTTPException(status_code=404, detail="任务不存在") from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{task_id}/results", response_model=EvaluationResult)
def get_task_result(task_id: str, db: Session = Depends(get_db)) -> EvaluationResult:
    result = evaluation_service.get_result(db, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="结果不存在")
    return result


@router.get("/{task_id}/progress")
def get_task_progress(task_id: str, db: Session = Depends(get_db)) -> dict:
    """
    获取任务执行进度

    返回任务状态和执行进度信息。
    """
    task = task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

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
            "message": f"任务状态：{_status_label(task.status)}"
        }
    except Exception:
        # Celery 不可用时返回基本状态
        return {
            "task_id": task_id,
            "status": task.status,
            "message": f"任务状态：{_status_label(task.status)}"
        }


def _status_label(status: str) -> str:
    return {
        "draft": "草稿",
        "scheduled": "已排队",
        "running": "运行中",
        "completed": "已完成",
        "failed": "失败",
    }.get(status, status)
