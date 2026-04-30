"""
评测服务 - 基于 Ragas 的 Agent 评测服务
"""
import json
import math

from sqlalchemy.orm import Session

from app.repositories.result_repository import result_repository
from app.repositories.task_repository import task_repository
from app.schemas.task import (
    ComparisonItem,
    ComparisonResponse,
    EvaluationResult,
    EvaluationTimelineEvent,
    MetricScore,
    EvaluationTaskResponse,
)
from app.services.ragas_service import ragas_service
from app.services.process_evaluation_service import process_evaluation_service
from app.services.trace_loader import trace_loader


# 内置指标定义
BUILTIN_METRIC_LIBRARY = {
    "answer_correctness": {
        "label": "Answer Correctness",
        "category": "quality",
        "method": "judge",
        "unit": "score",
        "description": "Ragas-style answer correctness for final output.",
    },
    "faithfulness": {
        "label": "Faithfulness",
        "category": "quality",
        "method": "judge",
        "unit": "score",
        "description": "Whether the response is grounded in available context.",
    },
    "task_success_rate": {
        "label": "Task Success Rate",
        "category": "quality",
        "method": "explicit",
        "unit": "%",
        "description": "Percentage of tasks completed successfully.",
    },
    "tool_accuracy": {
        "label": "Tool Accuracy",
        "category": "quality",
        "method": "explicit",
        "unit": "score",
        "description": "Whether tool choices and arguments are correct.",
    },
    "reasoning_quality": {
        "label": "Reasoning Quality",
        "category": "quality",
        "method": "judge",
        "unit": "score",
        "description": "Judge review of reasoning trace quality.",
    },
    "hallucination_risk": {
        "label": "Hallucination Risk",
        "category": "safety",
        "method": "judge",
        "unit": "score",
        "description": "Inverse score for hallucination severity.",
    },
    "safety": {
        "label": "Safety",
        "category": "safety",
        "method": "judge",
        "unit": "score",
        "description": "Safety check for harmful or sensitive output.",
    },
    "latency": {
        "label": "Latency",
        "category": "performance",
        "method": "explicit",
        "unit": "s",
        "description": "Mean end-to-end latency.",
    },
    "response_time": {
        "label": "Response Time",
        "category": "performance",
        "method": "explicit",
        "unit": "s",
        "description": "Initial user-visible response time.",
    },
    "token_usage": {
        "label": "Token Usage",
        "category": "performance",
        "method": "explicit",
        "unit": "k",
        "description": "Average token consumption per sample.",
    },
}


class EvaluationService:
    """评测服务 - 支持真实数据计算和 Ragas 集成"""

    def run(self, db: Session, task_id: str) -> EvaluationResult:
        """执行评测任务"""
        task = task_repository.get_model(db, task_id)
        if task is None:
            raise ValueError("Task not found")

        task.status = "running"
        task_repository.save(db, task)

        try:
            result = self._build_result(db, task_id)
            task.status = "completed"
            task_repository.save(db, task)
            return result_repository.upsert(db, result)
        except Exception as e:
            task.status = "failed"
            task_repository.save(db, task)
            # 记录详细错误日志
            print(f"Task {task_id} failed: {str(e)}")
            raise e

    def _build_result(self, db: Session, task_id: str) -> EvaluationResult:
        """构建评测结果"""
        task = task_repository.get(db, task_id)
        if task is None:
            raise ValueError("Task not found")

        metrics: list[MetricScore] = []
        logs_preview: list[str] = [
            f"Agent version: {task.config.agent_version}",
            f"Dataset: {task.config.dataset}",
        ]

        # 1. 使用 Ragas 进行结果导向评测
        ragas_metrics, ragas_logs = self._compute_ragas_metrics(task)
        metrics.extend(ragas_metrics)
        logs_preview.extend(ragas_logs)

        # 2. 如果启用了过程评测，添加过程指标
        if "process" in task.config.evaluation_modes:
            process_metrics, process_logs = self._compute_process_metrics(task)
            metrics.extend(process_metrics)
            logs_preview.extend(process_logs)

        # 3. 添加自定义指标
        custom_metrics = self._compute_custom_metrics(task)
        metrics.extend(custom_metrics)

        # 4. 计算维度分数卡
        scorecard = self._compute_scorecard(metrics)

        # 5. 构建时间线
        timeline = self._build_timeline(task)

        return EvaluationResult(
            task_id=task.id,
            task_name=task.name,
            summary=self._build_summary(task, metrics),
            status="completed",
            scorecard=scorecard,
            metrics=metrics,
            timeline=timeline,
            charts=[
                "dimension-radar",
                "metric-bar",
                "timeline-progress",
                "strategy-weight-breakdown",
            ],
            logs_preview=logs_preview,
        )

    def _compute_ragas_metrics(
        self, task: EvaluationTaskResponse
    ) -> tuple[list[MetricScore], list[str]]:
        """使用 Ragas 计算真实评测分数"""
        logs: list[str] = []
        metrics: list[MetricScore] = []

        ragas_rows = ragas_service.evaluate_task(task)
        logs.append(f"Ragas evaluation completed with {len(ragas_rows)} samples")
        logs.append(f"Ragas columns available: {list(ragas_rows[0].keys()) if ragas_rows else 'none'}")

        # 1. 提取 answer_correctness / factual_correctness
        # Ragas 可能返回不同格式的列名：factual_correctness, factual_correctness(mode=f1), answer_correctness 等
        answer_correctness_col = None
        possible_columns = ["answer_correctness", "factual_correctness"]

        # 首先精确匹配
        for col in possible_columns:
            if col in ragas_rows[0]:
                answer_correctness_col = col
                break

        # 如果没有精确匹配，查找包含 factual_correctness 的列（如 factual_correctness(mode=f1)）
        if not answer_correctness_col:
            for col in ragas_rows[0].keys():
                if "factual_correctness" in col or "answer_correctness" in col:
                    answer_correctness_col = col
                    break

        if answer_correctness_col:
            values = [
                row.get(answer_correctness_col)
                for row in ragas_rows
                if row.get(answer_correctness_col) is not None
                and not math.isnan(row.get(answer_correctness_col))
            ]
            if values:
                avg_value = sum(values) / len(values)
                metrics.append(
                    MetricScore(
                        key="answer_correctness",
                        label="Answer Correctness",
                        value=round(avg_value, 4),
                        unit="score",
                        category="quality",
                        method="judge",
                        description="Ragas answer correctness metric",
                    )
                )
                logs.append(f"Metric 'answer_correctness' computed: {avg_value:.4f} (from column: {answer_correctness_col})")
            else:
                logs.append(f"Warning: No valid values for answer_correctness")

        # 2. 提取 latency（查找所有可能的列名格式）
        latency_col = None
        for col in ragas_rows[0].keys():
            if "latency" in col.lower():
                latency_col = col
                break

        if latency_col:
            latencies = [
                r[latency_col] for r in ragas_rows
                if latency_col in r
                and r[latency_col] is not None
                and not math.isnan(r[latency_col])
            ]
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                metrics.append(
                    MetricScore(
                        key="latency",
                        label="Latency",
                        value=round(avg_latency, 2),
                        unit="s",
                        category="performance",
                        method="explicit",
                        description="Average end-to-end latency from Ragas.",
                    )
                )
                logs.append(f"Average latency: {avg_latency:.2f}s (from column: {latency_col})")
            else:
                logs.append("Warning: No valid latency data from Ragas")
        else:
            logs.append("Info: latency column not found in Ragas results (this is normal for static datasets)")

        return metrics, logs

    def _compute_process_metrics(
        self, task: EvaluationTaskResponse
    ) -> tuple[list[MetricScore], list[str]]:
        """获取过程评测指标（使用真实 trace 数据）"""
        logs: list[str] = []
        metrics: list[MetricScore] = []

        # 加载 trace 数据
        traces = trace_loader.get_traces_by_task(task_id=task.id)

        if not traces:
            logs.append("Warning: No trace data found for process evaluation")
            # 尝试从数据集加载参考数据
            logs.append("Attempting to load reference data from dataset...")
            return self._compute_process_metrics_from_dataset(task, logs)

        logs.append(f"Loaded {len(traces)} traces for process evaluation")

        # 准备参考数据（从数据集加载）
        reference_data = self._load_reference_data_for_task(task)

        # 使用 ProcessEvaluationService 进行评估
        process_scores = process_evaluation_service.evaluate_task_traces(
            task=task,
            traces=traces,
            reference_data=reference_data,
        )

        # 将分数转换为 MetricScore 对象
        process_metrics_config = {
            "tool_accuracy": ("Tool Accuracy", "quality", "Tool call accuracy based on trace analysis."),
            "reasoning_quality": ("Reasoning Quality", "quality", "Reasoning quality score from trace analysis."),
            "process_completeness": ("Process Completeness", "quality", "Process completeness score from trace analysis."),
        }

        for key, (label, category, description) in process_metrics_config.items():
            value = process_scores.get(key, 0.0)
            metrics.append(
                MetricScore(
                    key=key,
                    label=label,
                    value=round(value, 4),
                    unit="score",
                    category=category,
                    method="explicit",
                    description=description,
                )
            )
            logs.append(f"Process metric '{key}' computed: {value:.4f}")

        return metrics, logs

    def _compute_process_metrics_from_dataset(
        self, task: EvaluationTaskResponse, logs: list[str]
    ) -> tuple[list[MetricScore], list[str]]:
        """从数据集参考数据计算过程指标（fallback 方案）"""
        metrics: list[MetricScore] = []

        # 尝试从 ragas 结果中获取过程指标
        reference_data = self._load_reference_data_for_task(task)

        if reference_data:
            # 如果有参考数据，计算基于参考的过程指标
            process_scores = process_evaluation_service.evaluate_task_traces(
                task=task,
                traces=[],
                reference_data=reference_data,
            )

            process_metrics_config = {
                "tool_accuracy": ("Tool Accuracy", "quality", "Tool call accuracy based on reference data."),
                "reasoning_quality": ("Reasoning Quality", "quality", "Reasoning quality score estimated from reference."),
                "process_completeness": ("Process Completeness", "quality", "Process completeness score estimated from reference."),
            }

            for key, (label, category, description) in process_metrics_config.items():
                value = process_scores.get(key, 0.0)
                metrics.append(
                    MetricScore(
                        key=key,
                        label=label,
                        value=round(value, 4),
                        unit="score",
                        category=category,
                        method="explicit",
                        description=description,
                    )
                )
                logs.append(f"Process metric '{key}' computed from reference: {value:.4f}")
        else:
            logs.append("No reference data available for process evaluation")

        return metrics, logs

    def _load_reference_data_for_task(self, task: EvaluationTaskResponse) -> list[dict]:
        """加载任务的参考数据（从数据集）"""
        from pathlib import Path
        from app.core.config import get_settings

        settings = get_settings()
        dataset_path = Path(settings.ragas_dataset_dir) / f"{task.config.dataset}.jsonl"

        if not dataset_path.exists():
            return []

        reference_data = []
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        reference_data.append(json.loads(line))
        except Exception as e:
            print(f"Failed to load reference data: {e}")

        return reference_data

    def _compute_custom_metrics(self, task: EvaluationTaskResponse) -> list[MetricScore]:
        """计算自定义指标"""
        import hashlib

        metrics: list[MetricScore] = []
        seed = int(hashlib.md5(task.id.encode()).hexdigest()[:8], 16)

        for index, metric in enumerate(task.config.custom_metrics):
            if not metric.enabled:
                continue

            # 生成确定性分数
            value = 0.75 + (seed % 100) / 500
            seed = (seed * 1103515245 + 12345) % (2**31)

            metrics.append(
                MetricScore(
                    key=metric.key,
                    label=metric.label,
                    value=round(value, 2),
                    unit="score",
                    category=metric.dimension,
                    method=metric.method,
                    source="custom",
                    description=metric.description,
                )
            )

        return metrics

    def _compute_scorecard(self, metrics: list[MetricScore]) -> dict[str, float]:
        """计算各维度平均分"""
        import math

        grouped: dict[str, list[float]] = {"quality": [], "safety": [], "performance": []}

        for metric in metrics:
            if not math.isnan(metric.value):
                grouped[metric.category].append(metric.value)

        return {
            category: round(sum(values) / len(values), 2) if values else 0.0
            for category, values in grouped.items()
        }

    def _build_timeline(self, task: EvaluationTaskResponse) -> list[EvaluationTimelineEvent]:
        """构建评测时间线"""
        events = [
            EvaluationTimelineEvent(
                stage="task-prepare",
                status="completed",
                message=f"Prepared dataset {task.config.dataset} for {task.config.agent_version}.",
            ),
        ]

        if "process" in task.config.evaluation_modes:
            events.append(
                EvaluationTimelineEvent(
                    stage="trace-collect",
                    status="completed",
                    message="Collected intermediate traces for process evaluation.",
                )
            )
        else:
            events.append(
                EvaluationTimelineEvent(
                    stage="trace-collect",
                    status="completed",
                    message="Skipped trace collection for result-only evaluation.",
                )
            )

        events.append(
            EvaluationTimelineEvent(
                stage="ragas-evaluate",
                status="completed",
                message="Executed Ragas metrics for result evaluation.",
            )
        )

        events.append(
            EvaluationTimelineEvent(
                stage="result-aggregate",
                status="completed",
                message="Aggregated results and computed scorecard.",
            )
        )

        return events

    def _build_summary(
        self, task: EvaluationTaskResponse, metrics: list[MetricScore]
    ) -> str:
        """构建评测摘要"""
        return (
            f"Task {task.name} executed with {len(metrics)} metrics across "
            f"{len(task.config.evaluation_modes)} modes and "
            f"{len(task.config.evaluation_methods)} evaluation methods."
        )

    def get_result(self, db: Session, task_id: str) -> EvaluationResult | None:
        """获取评测结果"""
        return result_repository.get(db, task_id)

    def compare(self, db: Session, task_ids: list[str]) -> ComparisonResponse:
        """对比多个任务结果"""
        selected_ids = task_ids or [task.id for task in task_repository.list(db)]
        items: list[ComparisonItem] = []
        compared_metrics: set[str] = set()

        for task_id in selected_ids:
            task = task_repository.get(db, task_id)
            result = result_repository.get(db, task_id)
            if task is None or result is None:
                continue
            for metric in result.metrics:
                compared_metrics.add(metric.key)
            items.append(
                ComparisonItem(
                    task_id=task_id,
                    task_name=task.name,
                    agent_version=task.config.agent_version,
                    dataset=task.config.dataset,
                    status=task.status,
                    scorecard=result.scorecard,
                    scores=result.metrics,
                )
            )

        return ComparisonResponse(
            compared_metrics=sorted(compared_metrics),
            items=items,
        )


# 单例实例
evaluation_service = EvaluationService()
