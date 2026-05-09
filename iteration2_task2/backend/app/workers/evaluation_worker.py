"""
评测任务 Worker

处理异步评测任务执行。
"""

from celery import Task
from typing import Optional
import logging

from app.workers.celery_app import celery_app
from app.db.database import SessionLocal, get_db_session
from app.services.evaluation_service import evaluation_service
from app.services.task_service import task_service
from app.repositories.task_repository import task_repository

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """Base task class with database session support"""

    _db = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_db_session()
        return self._db

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(
    base=DatabaseTask,
    bind=True,
    name="app.workers.evaluation_worker.run_evaluation_task",
    max_retries=3,
    default_retry_delay=60,
)
def run_evaluation_task(self, task_id: str) -> dict:
    """
    异步执行评测任务

    Args:
        task_id: 评测任务 ID

    Returns:
        执行结果摘要
    """
    db = self.db

    try:
        # 更新任务状态为运行中
        task = task_repository.get(db, task_id)
        if task is None:
            logger.error(f"任务 {task_id} 不存在")
            return {"status": "failed", "error": "任务不存在"}

        task_repository.save(db, task)
        logger.info(f"开始执行评测任务 {task_id}")

        # 执行评测
        result = evaluation_service.run(db, task_id)

        logger.info(f"评测任务 {task_id} 执行完成")

        return {
            "status": "completed",
            "task_id": task_id,
            "task_name": result.task_name,
            "metrics_count": len(result.metrics),
            "scorecard": result.scorecard,
        }

    except Exception as exc:
        logger.error(f"评测任务 {task_id} 执行失败：{exc}")

        # 更新任务状态为失败
        try:
            task = task_repository.get(db, task_id)
            if task:
                task.status = "failed"
                task_repository.save(db, task)
        except Exception as e:
            logger.error(f"更新任务状态失败：{e}")

        # 重试
        if self.request.retries < self.max_retries:
            logger.info(f"重试任务 {task_id}，第 {self.request.retries + 1} 次")
            raise self.retry(exc=exc)
        else:
            return {"status": "failed", "error": str(exc)}


@celery_app.task(
    base=DatabaseTask,
    bind=True,
    name="app.workers.evaluation_worker.batch_run_evaluation_task",
    max_retries=3,
    default_retry_delay=120,
)
def batch_run_evaluation_tasks(self, task_ids: list[str]) -> dict:
    """
    批量异步执行评测任务

    Args:
        task_ids: 评测任务 ID 列表

    Returns:
        批量执行结果
    """
    results = []
    failed = []

    for task_id in task_ids:
        try:
            result = run_evaluation_task.delay(task_id)
            results.append({"task_id": task_id, "job_id": result.id})
        except Exception as exc:
            failed.append({"task_id": task_id, "error": str(exc)})

    return {
        "status": "submitted",
        "submitted": results,
        "failed": failed,
        "total": len(task_ids),
    }
