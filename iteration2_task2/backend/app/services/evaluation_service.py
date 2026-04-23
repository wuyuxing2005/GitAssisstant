from app.repositories.task_repository import task_repository
from app.schemas.task import ComparisonItem, ComparisonResponse, EvaluationResult, MetricScore


class EvaluationService:
    def __init__(self) -> None:
        self._results: dict[str, EvaluationResult] = {
            "eval-001": EvaluationResult(
                task_id="eval-001",
                summary="基线评测完成，整体效果良好，安全得分较高。",
                metrics=[
                    MetricScore(name="answer_correctness", value=0.86, category="效果"),
                    MetricScore(name="latency", value=1.72, category="性能"),
                    MetricScore(name="safety", value=0.93, category="安全"),
                ],
                charts=["score-radar", "latency-trend", "dimension-breakdown"],
                logs_preview=[
                    "Ragas evaluator initialized.",
                    "Dataset customer-support-v2 loaded.",
                    "Completed 120/120 samples.",
                ],
            )
        }

    def run(self, task_id: str) -> EvaluationResult:
        task = task_repository.get(task_id)
        if task is None:
            raise ValueError("Task not found")

        task.status = "running"
        result = EvaluationResult(
            task_id=task_id,
            summary="评测任务已触发，当前返回的是框架阶段的模拟结果。",
            metrics=[
                MetricScore(name="tool_accuracy", value=0.79, category="效果"),
                MetricScore(name="reasoning_quality", value=0.74, category="效果"),
                MetricScore(name="token_usage", value=0.68, category="性能"),
            ],
            charts=["comparison-bar", "judge-score-distribution"],
            logs_preview=[
                "Evaluation worker created.",
                "Process tracing enabled.",
                "Custom metrics hook loaded.",
            ],
        )
        task.status = "completed"
        self._results[task_id] = result
        return result

    def get_result(self, task_id: str) -> EvaluationResult | None:
        return self._results.get(task_id)

    def compare(self, task_ids: list[str]) -> ComparisonResponse:
        selected_ids = task_ids or list(self._results.keys())
        items: list[ComparisonItem] = []

        for task_id in selected_ids:
            task = task_repository.get(task_id)
            result = self._results.get(task_id)
            if task is None or result is None:
                continue
            items.append(
                ComparisonItem(
                    task_id=task_id,
                    task_name=task.name,
                    scores=result.metrics,
                )
            )

        return ComparisonResponse(
            compared_metrics=["answer_correctness", "latency", "safety", "tool_accuracy"],
            items=items,
        )


evaluation_service = EvaluationService()
