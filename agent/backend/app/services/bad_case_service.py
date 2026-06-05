from __future__ import annotations

from collections import Counter
from uuid import uuid4

from app.schemas.task import (
    BadCaseCreate,
    BadCaseRecord,
    BadCaseRerunRequest,
    BadCaseUpdate,
    DEFAULT_BAD_CASE_TAGS,
    EvaluationTaskCreate,
)
from app.services.task_service import task_service
from app.utils.time import now_local


def _metric_value(case: BadCaseRecord, name: str) -> float:
    for metric in case.metrics:
        if metric.name == name:
            return metric.value
    return 0.0


class BadCaseService:
    def __init__(self) -> None:
        self._cases: dict[str, BadCaseRecord] = {}

    def list_cases(self) -> list[BadCaseRecord]:
        return sorted(self._cases.values(), key=lambda case: case.updated_at, reverse=True)

    def get(self, case_id: str) -> BadCaseRecord | None:
        return self._cases.get(case_id)

    def _default_tags_for_status(self, status: str) -> list[str]:
        if status == "failed":
            return ["测试失败未恢复"]
        return []

    def _test_output_summary(self, timeline) -> str:
        for entry in reversed(timeline):
            if entry.event_type == "tool" and "run_pytest" in entry.title:
                return entry.content[:2000]
        return ""

    def _diff_summary(self, task_id: str) -> str:
        try:
            from app.services.evaluation_service import evaluation_service

            diff = evaluation_service.get_git_diff(task_id)
        except Exception:
            return ""
        if diff is None or not diff.diff.strip():
            return ""
        changed_files = [
            line.removeprefix("diff --git a/")
            for line in diff.diff.splitlines()
            if line.startswith("diff --git a/")
        ]
        return "\n".join(changed_files[:20]) or diff.diff[:2000]

    def create_from_task(self, payload: BadCaseCreate) -> BadCaseRecord:
        task = task_service.get_task(payload.task_id)
        if task is None:
            raise ValueError("Task not found")

        result = task.result
        tags = payload.tags or self._default_tags_for_status(task.status)
        now = now_local()
        record = BadCaseRecord(
            id=f"bad-{uuid4().hex[:8]}",
            source_task_id=task.id,
            task_name=task.name,
            issue_input=task.config.issue_input,
            status=task.status,
            tags=[tag for tag in tags if tag in DEFAULT_BAD_CASE_TAGS or tag.strip()],
            note=payload.note,
            agent_trace=result.agent_trace if result else None,
            timeline=list(result.timeline) if result else [],
            metrics=list(result.metrics) if result else [],
            diff_summary=self._diff_summary(task.id),
            test_output_summary=self._test_output_summary(result.timeline) if result else "",
            summary=result.summary if result else task.description,
            created_at=now,
            updated_at=now,
        )
        self._cases[record.id] = record
        return record

    def update(self, case_id: str, payload: BadCaseUpdate) -> BadCaseRecord | None:
        record = self._cases.get(case_id)
        if record is None:
            return None
        updated = record.model_copy(
            update={
                "tags": [tag for tag in payload.tags if tag.strip()],
                "note": payload.note,
                "updated_at": now_local(),
            }
        )
        self._cases[case_id] = updated
        return updated

    def delete(self, case_id: str) -> bool:
        return self._cases.pop(case_id, None) is not None

    def rerun(self, case_id: str, request: BadCaseRerunRequest):
        record = self._cases.get(case_id)
        if record is None:
            return None
        source = task_service.get_task(record.source_task_id)
        if source is None:
            raise ValueError("Source task not found")
        return task_service.create_task(
            EvaluationTaskCreate(
                name=request.name or f"复跑 {record.task_name}",
                description=f"由 Bad Case {record.id} 重新创建。{record.note}".strip(),
                config=source.config,
                auto_start=request.auto_start,
            )
        )

    def tag_counts(self, case_ids: set[str] | None = None) -> Counter[str]:
        counter: Counter[str] = Counter()
        for case in self.list_cases():
            if case_ids is not None and case.id not in case_ids:
                continue
            counter.update(case.tags)
        return counter

    def metric_value(self, case: BadCaseRecord, name: str) -> float:
        return _metric_value(case, name)


bad_case_service = BadCaseService()
