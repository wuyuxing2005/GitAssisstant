from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pathlib import Path
from app.db.database import get_db
from app.schemas.task import (
    CustomMetricDefinition,
    EvaluationMetadataResponse,
    EvaluationStrategy,
)
from app.core.config import get_settings

router = APIRouter()

settings = get_settings()


@router.get("/evaluation-options", response_model=EvaluationMetadataResponse)
def get_evaluation_options(db: Session = Depends(get_db)) -> EvaluationMetadataResponse:
    # 动态加载可用数据集列表
    datasets = []
    dataset_dir = Path(settings.ragas_dataset_dir)
    if dataset_dir.exists():
        for file in dataset_dir.glob("*.jsonl"):
            if not file.name.startswith("_temp_"):
                datasets.append(file.stem)

    return EvaluationMetadataResponse(
        modes=[
            {"key": "result", "label": "Result-oriented"},
            {"key": "process", "label": "Process-oriented"},
        ],
        methods=[
            {"key": "explicit", "label": "Explicit Metric"},
            {"key": "judge", "label": "LLM-as-a-Judge"},
        ],
        dimensions=[
            {"key": "quality", "label": "Quality"},
            {"key": "safety", "label": "Safety"},
            {"key": "performance", "label": "Performance"},
        ],
        builtin_metrics=[
            CustomMetricDefinition(
                key="answer_correctness",
                label="Answer Correctness",
                description="Result quality metric suitable for Ragas.",
                dimension="quality",
                method="judge",
            ),
            CustomMetricDefinition(
                key="faithfulness",
                label="Faithfulness",
                description="Checks grounding against available context.",
                dimension="quality",
                method="judge",
            ),
            CustomMetricDefinition(
                key="task_success_rate",
                label="Task Success Rate",
                description="Explicit completion rate across the dataset.",
                dimension="quality",
                method="explicit",
            ),
            CustomMetricDefinition(
                key="tool_accuracy",
                label="Tool Accuracy",
                description="Evaluates tool selection and argument correctness.",
                dimension="quality",
                method="explicit",
            ),
            CustomMetricDefinition(
                key="reasoning_quality",
                label="Reasoning Quality",
                description="Judge score for intermediate reasoning quality.",
                dimension="quality",
                method="judge",
            ),
            CustomMetricDefinition(
                key="hallucination_risk",
                label="Hallucination Risk",
                description="Judge score for hallucination severity.",
                dimension="safety",
                method="judge",
            ),
            CustomMetricDefinition(
                key="safety",
                label="Safety",
                description="Judge score for unsafe or policy-violating output.",
                dimension="safety",
                method="judge",
            ),
            CustomMetricDefinition(
                key="latency",
                label="Latency",
                description="Average full request latency.",
                dimension="performance",
                method="explicit",
            ),
            CustomMetricDefinition(
                key="response_time",
                label="Response Time",
                description="Initial user-visible response time.",
                dimension="performance",
                method="explicit",
            ),
            CustomMetricDefinition(
                key="token_usage",
                label="Token Usage",
                description="Average token usage per sample.",
                dimension="performance",
                method="explicit",
            ),
        ],
        strategy_templates=[
            EvaluationStrategy(
                key="balanced-default",
                label="Balanced Default",
                description="Balanced evaluation across quality, safety, and performance.",
                metric_keys=["answer_correctness", "safety", "latency"],
                weights={"answer_correctness": 0.4, "safety": 0.35, "latency": 0.25},
            ),
            EvaluationStrategy(
                key="trace-first",
                label="Trace First",
                description="Focus on reasoning trace and tool invocation quality.",
                metric_keys=["tool_accuracy", "reasoning_quality", "token_usage"],
                weights={
                    "tool_accuracy": 0.4,
                    "reasoning_quality": 0.35,
                    "token_usage": 0.25,
                },
            ),
            EvaluationStrategy(
                key="safety-guardrail",
                label="Safety Guardrail",
                description="Safety-first strategy suitable for user-facing agents.",
                metric_keys=["safety", "hallucination_risk", "response_time"],
                weights={"safety": 0.45, "hallucination_risk": 0.35, "response_time": 0.2},
            ),
        ],
        datasets=datasets,
        agent_versions=["v1.3.0", "v1.4.0-rc1", "v2.0.0-beta"],
    )
