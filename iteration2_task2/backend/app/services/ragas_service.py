from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.schemas.task import EvaluationTaskResponse

settings = get_settings()


class RagasService:
    def is_enabled(self) -> bool:
        return settings.ragas_enabled

    def evaluate_task(self, task: EvaluationTaskResponse) -> list[dict[str, Any]]:
        """
        Real Ragas integration entrypoint.

        Expected dataset file:
        - {ragas_dataset_dir}/{task.config.dataset}.jsonl

        Expected JSONL fields for result-oriented evaluation:
        - user_input
        - response
        - reference
        - retrieved_contexts

        Expected extra fields for process/tool evaluation:
        - reference_tool_calls
        - tool_calls
        - rubrics
        """
        if not self.is_enabled():
            raise RuntimeError("Ragas integration is disabled.")

        dataset_path = Path(settings.ragas_dataset_dir) / f"{task.config.dataset}.jsonl"
        if not dataset_path.exists():
            raise FileNotFoundError(f"Ragas dataset not found: {dataset_path}")

        try:
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings
            from ragas import EvaluationDataset, evaluate
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from ragas.llms import LangchainLLMWrapper
            from ragas.metrics import (
                AgentGoalAccuracy,
                FactualCorrectness,
                Faithfulness,
                SemanticSimilarity,
                ToolCallAccuracy,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Ragas dependencies are missing. Install backend extras for ragas execution."
            ) from exc

        llm = LangchainLLMWrapper(ChatOpenAI(model=settings.ragas_llm_model))
        embeddings = LangchainEmbeddingsWrapper(
            OpenAIEmbeddings(model=settings.ragas_embedding_model)
        )
        dataset = EvaluationDataset.from_jsonl(str(dataset_path))

        metric_map = {
            "faithfulness": Faithfulness(llm=llm),
            "answer_correctness": FactualCorrectness(llm=llm),
            "semantic_similarity": SemanticSimilarity(embeddings=embeddings),
            "tool_accuracy": ToolCallAccuracy(llm=llm),
            "task_success_rate": AgentGoalAccuracy(llm=llm),
        }
        metrics = [metric_map[key] for key in task.config.builtin_metrics if key in metric_map]
        if not metrics:
            metrics = [Faithfulness(llm=llm), FactualCorrectness(llm=llm)]

        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
            experiment_name=task.id,
            show_progress=False,
            raise_exceptions=False,
        )
        return result.to_pandas().to_dict(orient="records")


ragas_service = RagasService()
