"""
Celery 应用配置

用于异步任务队列处理评测任务。
"""

import os
from celery import Celery

# 从环境变量或默认值获取配置
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# 创建 Celery 应用
celery_app = Celery(
    "agent_eval",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["app.workers.evaluation_worker"],
)

# 配置 Celery
celery_app.conf.update(
    # 任务序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # 时区
    timezone="UTC",
    enable_utc=True,
    # 任务结果过期时间（秒）
    result_expires=3600,
    # 任务确认方式
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # 预取限制
    worker_prefetch_multiplier=1,
    # 任务超时配置
    task_time_limit=3600,  # 1 小时
    task_soft_time_limit=3300,  # 55 分钟
    # 重试配置
    task_default_retry_delay=60,
    task_max_retries=3,
)
