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
            agent_version="v1.3.0",
            dataset="customer-support-v2",
            evaluation_modes=["result"],
            evaluation_methods=["explicit", "judge"],
            dimensions=["quality", "safety", "performance"],
            builtin_metrics=["answer_correctness", "latency", "safety"],
            custom_metrics=[
                CustomMetricDefinition(
                    key="dialog_empathy",
                    label="Dialog Empathy",
                    description="Judge whether the tone fits a support scenario.",
                    dimension="quality",
                    method="judge",
                )
            ],
            strategy=EvaluationStrategy(
                key="balanced-default",
                label="Balanced Default",
                description="Blend quality, safety, and performance with equal attention.",
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
            name="Customer Support Agent Baseline",
            description="Evaluate answer quality, latency, and safety for the customer support workflow.",
            status="completed",
            config=task_config.model_dump(mode="json"),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        result = EvaluationResult(
            task_id="eval-001",
            task_name="Customer Support Agent Baseline",
            summary="Balanced result/process review completed. Quality and safety are stable, but latency still has optimization room.",
            status="completed",
            scorecard={"quality": 0.84, "safety": 0.93, "performance": 1.72},
            metrics=[
                MetricScore(
                    key="answer_correctness",
                    label="Answer Correctness",
                    value=0.86,
                    category="quality",
                    method="judge",
                ),
                MetricScore(
                    key="latency",
                    label="Latency",
                    value=1.72,
                    unit="s",
                    category="performance",
                    method="explicit",
                ),
                MetricScore(
                    key="safety",
                    label="Safety",
                    value=0.93,
                    category="safety",
                    method="judge",
                ),
            ],
            timeline=[
                EvaluationTimelineEvent(
                    stage="dataset-load",
                    status="completed",
                    message="Loaded 120 samples from customer-support-v2.",
                ),
                EvaluationTimelineEvent(
                    stage="ragas-run",
                    status="completed",
                    message="Executed Ragas metrics for result evaluation.",
                ),
            ],
            charts=["score-radar", "latency-trend", "dimension-breakdown"],
            logs_preview=[
                "Ragas evaluator initialized.",
                "Trace collector disabled for result-only rows.",
                "Completed 120/120 samples.",
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
