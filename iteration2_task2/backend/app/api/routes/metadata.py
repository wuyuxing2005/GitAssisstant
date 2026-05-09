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
from app.services.judge_prompts import get_available_templates

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
            {"key": "result", "label": "面向结果"},
            {"key": "process", "label": "面向过程"},
        ],
        methods=[
            {"key": "explicit", "label": "显式指标"},
            {"key": "judge", "label": "LLM 评审"},
        ],
        dimensions=[
            {"key": "quality", "label": "效果"},
            {"key": "safety", "label": "安全"},
            {"key": "performance", "label": "性能"},
        ],
        builtin_metrics=[
            CustomMetricDefinition(
                key="answer_correctness",
                label="答案正确性",
                description="评估最终回答与参考答案是否一致、准确和完整。",
                dimension="quality",
                method="judge",
            ),
            CustomMetricDefinition(
                key="faithfulness",
                label="忠实性",
                description="评估回答是否忠实于检索上下文，是否有依据。",
                dimension="quality",
                method="judge",
            ),
            CustomMetricDefinition(
                key="task_success_rate",
                label="任务成功率",
                description="基于成功标记、参考答案或最终回答计算任务完成情况。",
                dimension="quality",
                method="explicit",
            ),
            CustomMetricDefinition(
                key="tool_accuracy",
                label="工具调用准确率",
                description="评估工具选择和参数是否与参考工具调用一致。",
                dimension="quality",
                method="explicit",
            ),
            CustomMetricDefinition(
                key="reasoning_quality",
                label="推理质量",
                description="评估中间推理过程是否清晰、必要且符合任务目标。",
                dimension="quality",
                method="judge",
            ),
            CustomMetricDefinition(
                key="hallucination_risk",
                label="幻觉控制",
                description="评估回答是否避免编造事实，分数越高代表幻觉风险越低。",
                dimension="safety",
                method="judge",
            ),
            CustomMetricDefinition(
                key="safety",
                label="安全性",
                description="评估回答是否安全、无害，并避免敏感或违规内容。",
                dimension="safety",
                method="judge",
            ),
            CustomMetricDefinition(
                key="latency",
                label="延迟得分",
                description="基于端到端延迟字段或执行链路延迟计算响应速度。",
                dimension="performance",
                method="explicit",
            ),
            CustomMetricDefinition(
                key="response_time",
                label="首响应得分",
                description="基于首响应时间或首 Token 时间计算用户可感知速度。",
                dimension="performance",
                method="explicit",
            ),
            CustomMetricDefinition(
                key="token_usage",
                label="Token 效率",
                description="基于 Token 消耗计算资源使用效率。",
                dimension="performance",
                method="explicit",
            ),
            CustomMetricDefinition(
                key="interaction_experience",
                label="交互体验",
                description="评估回答是否有帮助、表达顺畅且符合用户体验。",
                dimension="performance",
                method="judge",
            ),
        ],
        strategy_templates=[
            EvaluationStrategy(
                key="balanced-default",
                label="均衡默认策略",
                description="同时覆盖效果、安全和性能的通用评测策略。",
                metric_keys=["answer_correctness", "faithfulness", "safety", "latency", "token_usage"],
                weights={
                    "answer_correctness": 0.25,
                    "faithfulness": 0.2,
                    "safety": 0.25,
                    "latency": 0.15,
                    "token_usage": 0.15,
                },
            ),
            EvaluationStrategy(
                key="trace-first",
                label="过程优先策略",
                description="重点关注推理过程、工具调用和过程完整性。",
                metric_keys=["tool_accuracy", "task_success_rate", "reasoning_quality", "token_usage"],
                weights={
                    "tool_accuracy": 0.35,
                    "task_success_rate": 0.25,
                    "reasoning_quality": 0.25,
                    "token_usage": 0.15,
                },
            ),
            EvaluationStrategy(
                key="safety-guardrail",
                label="安全护栏策略",
                description="面向用户场景的安全优先评测策略。",
                metric_keys=["safety", "hallucination_risk", "answer_correctness", "response_time"],
                weights={
                    "safety": 0.35,
                    "hallucination_risk": 0.3,
                    "answer_correctness": 0.2,
                    "response_time": 0.15,
                },
            ),
        ],
        datasets=datasets,
    )


@router.get("/judge-prompts")
def get_judge_prompts() -> list[dict]:
    """获取所有可用的 Judge 提示词模板"""
    return get_available_templates()
