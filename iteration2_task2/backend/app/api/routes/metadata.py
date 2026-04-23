from fastapi import APIRouter

from app.schemas.task import EvaluationMetadataResponse

router = APIRouter()


@router.get("/evaluation-options", response_model=EvaluationMetadataResponse)
def get_evaluation_options() -> EvaluationMetadataResponse:
    return EvaluationMetadataResponse(
        modes=["面向结果", "面向过程"],
        methods=["显式指标", "模糊指标", "LLM-as-a-Judge"],
        dimensions=["效果", "安全", "性能"],
        builtin_metrics=[
            "answer_correctness",
            "faithfulness",
            "latency",
            "token_usage",
            "tool_accuracy",
            "safety",
        ],
        strategy_templates=["标准组合策略", "过程+结果混合策略", "安全优先策略"],
    )
