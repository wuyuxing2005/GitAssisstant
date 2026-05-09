from datetime import datetime

from app.db.database import Base, SessionLocal, engine
from app.db.models import EvaluationResultORM, TaskORM
from app.schemas.task import (
    CustomMetricDefinition,
    EvaluationConfig,
    EvaluationResult,
    EvaluationStrategy,
    EvaluationTimelineEvent,
    MetricScore,
)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def seed_db() -> None:
    with SessionLocal() as db:
        if db.query(TaskORM).first() is not None:
            return

        task_config = EvaluationConfig(
            dataset="customer-support-v2",
            evaluation_modes=["result"],
            evaluation_methods=["explicit", "judge"],
            dimensions=["quality", "safety", "performance"],
            builtin_metrics=["answer_correctness", "safety", "latency", "token_usage"],
            custom_metrics=[
                CustomMetricDefinition(
                    key="dialog_empathy",
                    label="对话同理心",
                    description="评估回答语气是否符合客服支持场景。",
                    dimension="quality",
                    method="judge",
                )
            ],
            strategy=EvaluationStrategy(
                key="balanced-default",
                label="均衡默认策略",
                description="均衡覆盖效果、安全和性能。",
                metric_keys=["answer_correctness", "latency", "safety", "dialog_empathy"],
                weights={
                    "answer_correctness": 0.35,
                    "safety": 0.3,
                    "latency": 0.2,
                    "dialog_empathy": 0.15,
                },
            ),
        )

        task = TaskORM(
            id="eval-001",
            name="客服 Agent 基线评测",
            description="评估客服流程中的回答质量、延迟和安全性。",
            status="completed",
            config=task_config.model_dump(mode="json"),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        result = EvaluationResult(
            task_id="eval-001",
            task_name="客服 Agent 基线评测",
            summary="均衡评测已完成，效果和安全表现稳定，延迟仍有优化空间。",
            status="completed",
            scorecard={"quality": 0.84, "safety": 0.93, "performance": 1.72},
            metrics=[
                MetricScore(
                    key="answer_correctness",
                    label="答案正确性",
                    value=0.86,
                    category="quality",
                    method="judge",
                ),
                MetricScore(
                    key="latency",
                    label="延迟得分",
                    value=1.72,
                    unit="s",
                    category="performance",
                    method="explicit",
                ),
                MetricScore(
                    key="safety",
                    label="安全性",
                    value=0.93,
                    category="safety",
                    method="judge",
                ),
            ],
            timeline=[
                EvaluationTimelineEvent(
                    stage="dataset-load",
                    status="completed",
                    message="已从 customer-support-v2 加载 120 条样本。",
                ),
                EvaluationTimelineEvent(
                    stage="ragas-run",
                    status="completed",
                    message="已执行面向结果的 Ragas 指标。",
                ),
            ],
            charts=["score-radar", "latency-trend", "dimension-breakdown"],
            logs_preview=[
                "Ragas 评估器已初始化。",
                "仅结果数据未启用执行链路采集。",
                "已完成 120/120 条样本。",
            ],
        )

        task.result = EvaluationResultORM(
            task_id=task.id,
            payload=result.model_dump(mode="json"),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(task)
        db.commit()
