from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.task import EvaluationTaskRecord
from app.schemas.task import (
    ComparisonItem,
    ComparisonResponse,
    EvaluationResult,
    MetricScore,
    RuntimeSnapshot,
    TaskRunRequest,
    TimelineEntry,
    ToolCallRecord,
    ToolUsageItem,
)
from app.services.task_service import task_service

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
EDIT_TOOL_NAMES = {"write_file", "replace_in_file", "patch_file"}
TEST_TOOL_NAMES = {"run_pytest"}
TERMINAL_TASK_STATUSES = {"completed", "failed"}


@dataclass
class AssistantRuntimeHandle:
    orchestrator: Any
    manager: Any
    thread_id: str


def _utcnow() -> datetime:
    return datetime.utcnow()


def _serialize_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def _tool_calls_from_message(message: Any) -> list[dict[str, Any]]:
    return list(getattr(message, "tool_calls", []) or [])


def _to_tool_call_records(tool_calls: list[dict[str, Any]]) -> list[ToolCallRecord]:
    return [
        ToolCallRecord(
            name=str(tool_call.get("name", "unknown_tool")),
            args=dict(tool_call.get("args", {}) or {}),
        )
        for tool_call in tool_calls
    ]


@lru_cache
def _assistant_components() -> tuple[Any, Any, Any, Any]:
    if str(WORKSPACE_ROOT) not in sys.path:
        sys.path.insert(0, str(WORKSPACE_ROOT))

    from dotenv import load_dotenv

    load_dotenv(WORKSPACE_ROOT / ".env")

    from gitIssueAssitant.agent import Agent, LLM_factory
    from gitIssueAssitant.orchestrator import AgentOrchestrator
    from gitIssueAssitant.session_manager import SessionManager

    return Agent, AgentOrchestrator, SessionManager, LLM_factory


class EvaluationService:
    def __init__(self) -> None:
        self._runtime_handles: dict[str, AssistantRuntimeHandle] = {}
        self._background_jobs: dict[str, asyncio.Task[None]] = {}
        self._execution_lock = asyncio.Lock()

    def _blank_result(self, task: EvaluationTaskRecord) -> EvaluationResult:
        return EvaluationResult(
            task_id=task.id,
            summary="任务已创建，等待执行。",
            outcome="not_started",
            current_state=RuntimeSnapshot(
                thread_id=task.thread_id,
                repo_path=task.repo_path,
                issue_description=task.config.issue_input,
                status="INIT",
                max_iterations=task.config.max_iterations,
            ),
            started_at=task.started_at,
            finished_at=task.finished_at,
        )

    def _ensure_result(self, task: EvaluationTaskRecord) -> EvaluationResult:
        if task.result is None:
            task.result = self._blank_result(task)
        return task.result

    def _activate_runtime(self, handle: AssistantRuntimeHandle) -> None:
        os.environ["GIT_ISSUE_ASSISTANT_HOME"] = str(WORKSPACE_ROOT)
        if handle.manager.current_repo:
            os.environ["GIT_ISSUE_ASSISTANT_REPO_ROOT"] = handle.manager.current_repo
            os.chdir(handle.manager.current_repo)

    def _build_runtime_sync(self, task: EvaluationTaskRecord) -> AssistantRuntimeHandle:
        Agent, AgentOrchestrator, SessionManager, LLM_factory = _assistant_components()

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("缺少 OPENAI_API_KEY，无法启动 gitIssueAssitant。")

        os.environ["GIT_ISSUE_ASSISTANT_HOME"] = str(WORKSPACE_ROOT)
        original_model_name = os.getenv("MODEL_NAME")
        try:
            if task.config.model_name:
                os.environ["MODEL_NAME"] = task.config.model_name
            llm = LLM_factory()
        finally:
            if original_model_name is None:
                os.environ.pop("MODEL_NAME", None)
            else:
                os.environ["MODEL_NAME"] = original_model_name

        agent = Agent(llm)
        orchestrator = AgentOrchestrator(agent)
        manager = SessionManager(orchestrator, workspace_root=WORKSPACE_ROOT)
        manager.create_or_switch_session(task.config.repo_source, task.config.target_dir)
        manager.set_issue(task.config.issue_input)
        thread_id = manager.get_current_thread_id()
        config = {"configurable": {"thread_id": thread_id}}
        orchestrator.graph.update_state(config, {"max_iterations": task.config.max_iterations})

        return AssistantRuntimeHandle(
            orchestrator=orchestrator,
            manager=manager,
            thread_id=thread_id,
        )

    async def _ensure_runtime(
        self,
        task: EvaluationTaskRecord,
        *,
        reset: bool,
    ) -> AssistantRuntimeHandle:
        needs_rebuild = reset or task.id not in self._runtime_handles or task.status in TERMINAL_TASK_STATUSES
        if needs_rebuild:
            handle = await asyncio.to_thread(self._build_runtime_sync, task)
            self._runtime_handles[task.id] = handle
            task.thread_id = handle.thread_id
            task.repo_path = handle.manager.current_repo
            result = self._blank_result(task)
            result.summary = "任务上下文已初始化，等待执行。"
            task.result = result
            task.status = "scheduled"
            task.started_at = None
            task.finished_at = None
            task_service.save_task_record(task)
            return handle

        handle = self._runtime_handles[task.id]
        self._activate_runtime(handle)
        return handle

    def _state_snapshot(self, task: EvaluationTaskRecord, state: dict[str, Any]) -> RuntimeSnapshot:
        messages = state.get("messages") or []
        last_message = ""
        if messages:
            last_message = _serialize_content(getattr(messages[-1], "content", ""))

        return RuntimeSnapshot(
            thread_id=task.thread_id,
            repo_path=state.get("repo_path") or task.repo_path,
            issue_description=state.get("issue_description") or task.config.issue_input,
            status=str(state.get("status") or "INIT"),
            iteration_count=int(state.get("iteration_count") or 0),
            max_iterations=int(state.get("max_iterations") or task.config.max_iterations),
            plan=[str(item) for item in (state.get("plan") or [])],
            reflexion_notes=str(state.get("reflexion_notes") or ""),
            last_message=last_message,
        )

    def _map_task_status(self, runtime_status: str) -> str:
        if runtime_status == "SUCCESS":
            return "completed"
        if runtime_status == "FAILED":
            return "failed"
        if runtime_status == "INIT":
            return "scheduled"
        return "running"

    def _append_timeline_entries(
        self,
        task: EvaluationTaskRecord,
        node_name: str,
        payload: dict[str, Any],
    ) -> None:
        result = self._ensure_result(task)
        created_at = _utcnow()

        def next_id() -> str:
            return f"{task.id}-event-{len(result.timeline) + 1}"

        if node_name == "planner":
            plan_content = "\n".join(str(item) for item in (payload.get("plan") or []) if item)
            result.timeline.append(
                TimelineEntry(
                    id=next_id(),
                    node="planner",
                    event_type="plan",
                    title="生成修复计划",
                    content=plan_content,
                    created_at=created_at,
                )
            )
            return

        if node_name == "react":
            messages = payload.get("messages") or []
            ai_message = messages[-1] if messages else None
            tool_calls = _tool_calls_from_message(ai_message)
            result.timeline.append(
                TimelineEntry(
                    id=next_id(),
                    node="react",
                    event_type="assistant",
                    title="Agent 思考",
                    content=_serialize_content(getattr(ai_message, "content", "")),
                    tool_calls=_to_tool_call_records(tool_calls),
                    created_at=created_at,
                )
            )
            return

        if node_name == "reflect":
            result.timeline.append(
                TimelineEntry(
                    id=next_id(),
                    node="reflect",
                    event_type="reflection",
                    title="反思与重新规划",
                    content=str(payload.get("reflexion_notes") or ""),
                    created_at=created_at,
                )
            )
            return

        if node_name == "tools":
            for message in payload.get("messages") or []:
                tool_name = getattr(message, "name", None) or getattr(message, "tool_call_id", None) or "tool"
                result.timeline.append(
                    TimelineEntry(
                        id=next_id(),
                        node="tools",
                        event_type="tool",
                        title=f"工具输出：{tool_name}",
                        content=_serialize_content(getattr(message, "content", "")),
                        created_at=created_at,
                    )
                )

    def _tool_usage_from_result(self, result: EvaluationResult) -> list[ToolUsageItem]:
        counter: Counter[str] = Counter()
        for entry in result.timeline:
            for tool_call in entry.tool_calls:
                counter[tool_call.name] += 1

        return [
            ToolUsageItem(name=name, count=count)
            for name, count in counter.most_common()
        ]

    def _build_metrics(
        self,
        task: EvaluationTaskRecord,
        result: EvaluationResult,
    ) -> list[MetricScore]:
        snapshot = result.current_state or RuntimeSnapshot(max_iterations=task.config.max_iterations)
        tool_usage = {item.name: item.count for item in result.tool_usage}
        duration_seconds = 0.0
        if task.started_at:
            end_time = task.finished_at or _utcnow()
            duration_seconds = max((end_time - task.started_at).total_seconds(), 0.0)

        return [
            MetricScore(
                name="success",
                value=1.0 if task.status == "completed" else 0.0,
                category="结果",
                unit="布尔",
                description="是否达到 TASK_SUCCESS 终态。",
            ),
            MetricScore(
                name="iteration_count",
                value=float(snapshot.iteration_count),
                category="流程",
                unit="次",
                description="ReAct 执行轮数。",
            ),
            MetricScore(
                name="tool_call_count",
                value=float(sum(item.count for item in result.tool_usage)),
                category="工具",
                unit="次",
                description="Agent 发起的工具调用总数。",
            ),
            MetricScore(
                name="file_edit_count",
                value=float(sum(tool_usage.get(name, 0) for name in EDIT_TOOL_NAMES)),
                category="工具",
                unit="次",
                description="代码修改相关工具调用次数。",
            ),
            MetricScore(
                name="test_run_count",
                value=float(sum(tool_usage.get(name, 0) for name in TEST_TOOL_NAMES)),
                category="验证",
                unit="次",
                description="pytest 工具调用次数。",
            ),
            MetricScore(
                name="duration_seconds",
                value=duration_seconds,
                category="性能",
                unit="秒",
                description="从开始执行到当前或结束时的耗时。",
            ),
        ]

    def _refresh_result(self, task: EvaluationTaskRecord) -> None:
        result = self._ensure_result(task)
        result.tool_usage = self._tool_usage_from_result(result)
        result.metrics = self._build_metrics(task, result)
        result.logs_preview = [
            f"{entry.created_at.strftime('%H:%M:%S')} {entry.title}: "
            f"{(entry.content.splitlines()[0] if entry.content else '无输出')}"
            for entry in result.timeline[-12:]
        ]

        if task.status == "completed":
            result.outcome = "completed"
            result.summary = (
                f"任务执行完成，仓库已定位到 {task.repo_path or task.config.repo_source}，"
                f"共执行 {result.current_state.iteration_count if result.current_state else 0} 轮。"
            )
        elif task.status == "failed":
            result.outcome = "failed"
            result.summary = result.error_message or "任务执行失败。"
        elif task.status == "running":
            result.outcome = "running"
            result.summary = (
                f"任务执行中，当前已完成 {result.current_state.iteration_count if result.current_state else 0} 轮推理。"
            )
        elif task.status == "scheduled":
            result.outcome = "running" if task.started_at else "not_started"
            result.summary = "任务上下文已初始化，等待执行。"
        else:
            result.outcome = "not_started"
            result.summary = "任务已创建，等待执行。"

        result.started_at = task.started_at
        result.finished_at = task.finished_at

    def _sync_state(self, task: EvaluationTaskRecord, state: dict[str, Any]) -> None:
        result = self._ensure_result(task)
        result.current_state = self._state_snapshot(task, state)
        task.repo_path = result.current_state.repo_path or task.repo_path
        task.thread_id = result.current_state.thread_id or task.thread_id
        mapped_status = self._map_task_status(result.current_state.status)
        task.status = mapped_status  # type: ignore[assignment]

        if task.status == "running" and task.started_at is None:
            task.started_at = _utcnow()
        if task.status in TERMINAL_TASK_STATUSES:
            task.finished_at = task.finished_at or _utcnow()

        self._refresh_result(task)

    def _mark_failed(self, task: EvaluationTaskRecord, error_message: str) -> None:
        result = self._ensure_result(task)
        task.status = "failed"
        task.finished_at = _utcnow()
        result.error_message = error_message
        result.current_state = result.current_state or RuntimeSnapshot(
            thread_id=task.thread_id,
            repo_path=task.repo_path,
            issue_description=task.config.issue_input,
            status="FAILED",
            max_iterations=task.config.max_iterations,
        )
        result.current_state.status = "FAILED"
        self._refresh_result(task)
        task_service.save_task_record(task)

    async def _run_graph(
        self,
        task: EvaluationTaskRecord,
        handle: AssistantRuntimeHandle,
        *,
        mode: str,
    ) -> None:
        self._activate_runtime(handle)
        config = {"configurable": {"thread_id": handle.thread_id}}
        task.status = "running"
        task.started_at = task.started_at or _utcnow()
        self._refresh_result(task)
        task_service.save_task_record(task)

        if mode == "step":
            async for event in handle.orchestrator.graph.astream(None, config=config, stream_mode="updates"):
                node_name = next(iter(event))
                self._append_timeline_entries(task, node_name, event[node_name])
                state = handle.orchestrator.graph.get_state(config).values
                self._sync_state(task, state)
                task_service.save_task_record(task)
                break
        else:
            async for event in handle.orchestrator.graph.astream(None, config=config, stream_mode="updates"):
                node_name = next(iter(event))
                self._append_timeline_entries(task, node_name, event[node_name])
                state = handle.orchestrator.graph.get_state(config).values
                self._sync_state(task, state)
                task_service.save_task_record(task)

        final_state = handle.orchestrator.graph.get_state(config).values
        self._sync_state(task, final_state)
        self._refresh_result(task)
        task_service.save_task_record(task)

    async def _execute(
        self,
        task_id: str,
        request: TaskRunRequest,
    ) -> None:
        async with self._execution_lock:
            task = task_service.get_task_record(task_id)
            if task is None:
                return

            try:
                handle = await self._ensure_runtime(task, reset=request.reset)
                await self._run_graph(task, handle, mode=request.mode or task.config.run_mode)
            except Exception as exc:
                self._mark_failed(task, str(exc))
            finally:
                job = self._background_jobs.get(task_id)
                if job is not None and job.done():
                    self._background_jobs.pop(task_id, None)

    async def run(self, task_id: str, request: TaskRunRequest) -> EvaluationTaskRecord:
        task = task_service.get_task_record(task_id)
        if task is None:
            raise ValueError("Task not found")

        job = self._background_jobs.get(task_id)
        if job is not None and not job.done():
            return task

        request_mode = request.mode or task.config.run_mode
        run_request = TaskRunRequest(mode=request_mode, reset=request.reset)

        if request_mode == "auto":
            if any(not background_job.done() for task_key, background_job in self._background_jobs.items() if task_key != task_id):
                raise RuntimeError("当前已有其他任务在运行，gitIssueAssitant 运行时暂不支持并发执行。")

            task.status = "scheduled"
            self._refresh_result(task)
            task_service.save_task_record(task)
            self._background_jobs[task_id] = asyncio.create_task(self._execute(task_id, run_request))
            return task

        await self._execute(task_id, run_request)
        latest_task = task_service.get_task_record(task_id)
        if latest_task is None:
            raise ValueError("Task not found")
        return latest_task

    def get_result(self, task_id: str) -> EvaluationResult | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        self._refresh_result(task)
        task_service.save_task_record(task)
        return self._ensure_result(task)

    def clear_task_state(self, task_id: str) -> None:
        job = self._background_jobs.pop(task_id, None)
        if job is not None and not job.done():
            job.cancel()
        self._runtime_handles.pop(task_id, None)

    def compare(self, task_ids: list[str]) -> ComparisonResponse:
        tasks = task_service.list_tasks()
        selected_ids = set(task_ids) if task_ids else {task.id for task in tasks}
        items: list[ComparisonItem] = []
        compared_metric_names: list[str] = []

        for task_response in tasks:
            if task_response.id not in selected_ids:
                continue
            result = task_response.result or self.get_result(task_response.id)
            if result is None:
                continue
            compared_metric_names.extend(metric.name for metric in result.metrics)
            items.append(
                ComparisonItem(
                    task_id=task_response.id,
                    task_name=task_response.name,
                    status=task_response.status,
                    summary=result.summary,
                    scores=result.metrics,
                )
            )

        return ComparisonResponse(
            compared_metrics=sorted(set(compared_metric_names)),
            items=items,
        )


evaluation_service = EvaluationService()
