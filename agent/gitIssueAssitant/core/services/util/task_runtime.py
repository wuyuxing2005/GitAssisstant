"""Private task runtime used only by IssueAssistantService."""
from __future__ import annotations

import asyncio
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from gitIssueAssitant.core.schemas.task import TaskRecord
from gitIssueAssitant.core.schemas.task import (
    AgentTrace,
    ComparisonAggregate,
    ComparisonItem,
    ComparisonResponse,
    TaskResult,
    FixReport,
    GitDiffResponse,
    GitPullRequestRequest,
    GitPullRequestResponse,
    GitPushRequest,
    GitPushResponse,
    MetricScore,
    RuntimeSnapshot,
    TaskMessage,
    TaskMessageCreate,
    TaskMessageList,
    TaskRunRequest,
    TimelineEntry,
    ToolCallRecord,
    ToolUsageItem,
)
from gitIssueAssitant.core.services.skill_service import skill_service
from gitIssueAssitant.core.services.issue_assistant_service import IssueAssistantService
from gitIssueAssitant.core.agent.tools.sandbox_manager import SandboxManager
from gitIssueAssitant.core.services.task_service import task_service
from gitIssueAssitant.core.services.trace_service import agent_trace_service
from gitIssueAssitant.core.utils.time import now_local

WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
ENV_FILES = (
    WORKSPACE_ROOT / ".env",
)
EDIT_TOOL_NAMES = {"write_file", "replace_in_file", "patch_file"}
TEST_TOOL_NAMES = {"run_pytest"}
TERMINAL_TASK_STATUSES = {"completed", "failed"}
SANDBOX_UNAVAILABLE_STATUS = "SANDBOX_UNAVAILABLE"
AGENT_CONTROL_MESSAGE_LINES = {"GOAL_DONE", "TASK_SUCCESS", "TASK_FAILED"}


@dataclass
class _AssistantRuntimeHandle:
    assistant: IssueAssistantService
    thread_id: str
    initial_state: dict[str, Any] = field(default_factory=dict)
    sandbox_error: str = ""


def _utcnow() -> datetime:
    return now_local()


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


def _strip_agent_control_lines(content: str) -> str:
    lines = [
        line
        for line in content.splitlines()
        if line.strip() not in AGENT_CONTROL_MESSAGE_LINES
    ]
    return "\n".join(lines).strip()


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


def _load_runtime_env() -> None:
    from dotenv import load_dotenv

    for env_file in ENV_FILES:
        if env_file.exists():
            load_dotenv(env_file, override=False)


def _repair_windows_path_escapes(value: str) -> str:
    if os.name != "nt":
        return value
    return (
        value
        .replace("\r", r"\r")
        .replace("\n", r"\n")
        .replace("\t", r"\t")
    )


def _configured_clone_root() -> Path:
    configured = _repair_windows_path_escapes(
        os.getenv("GIT_ISSUE_ASSISTANT_CLONE_ROOT", "").strip()
    )
    if not configured:
        return WORKSPACE_ROOT / "repos"
    clone_root = Path(configured).expanduser()
    if not clone_root.is_absolute():
        clone_root = (WORKSPACE_ROOT / clone_root).resolve()
    clone_root.mkdir(parents=True, exist_ok=True)
    return clone_root


class _IssueAssistantTaskRuntime:
    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = Path(workspace_root or WORKSPACE_ROOT).resolve()
        self._runtime_handles: dict[str, _AssistantRuntimeHandle] = {}
        self._background_jobs: dict[str, asyncio.Task[None]] = {}
        self._execution_lock = asyncio.Lock()
        self._sandbox_manager: Any | None = None

    def _prune_finished_background_job(self, task_id: str) -> None:
        job = self._background_jobs.get(task_id)
        if job is not None and job.done():
            self._background_jobs.pop(task_id, None)

    def _track_background_job(self, task_id: str, job: asyncio.Task[None]) -> None:
        self._background_jobs[task_id] = job

        def cleanup(completed_job: asyncio.Task[None]) -> None:
            if self._background_jobs.get(task_id) is completed_job:
                self._background_jobs.pop(task_id, None)

        job.add_done_callback(cleanup)

    def _get_sandbox_manager(self, SandboxManager: Any) -> Any | None:
        disabled = os.getenv("GIT_ISSUE_ASSISTANT_DISABLE_SANDBOX", "").lower() in ("1", "true", "yes")
        if disabled:
            if self._sandbox_manager is not None:
                self._sandbox_manager.stop_all()
                self._sandbox_manager = None
            return None
        if self._sandbox_manager is None:
            self._sandbox_manager = SandboxManager(workspace_root=self.workspace_root / "workspaces")
        return self._sandbox_manager

    def _blank_result(self, task: TaskRecord) -> TaskResult:
        return TaskResult(
            task_id=task.id,
            summary="任务已创建，等待执行。",
            messages=[
                TaskMessage(
                    id=f"{task.id}-msg-1",
                    role="system",
                    content=f"任务已创建：{task.config.issue_input}",
                    created_at=_utcnow(),
                )
            ],
            outcome="not_started",
            current_state=RuntimeSnapshot(
                thread_id=task.thread_id,
                repo_path=task.repo_path,
                issue_description=task.config.issue_input,
                status="INIT",
            ),
            started_at=task.started_at,
            finished_at=task.finished_at,
        )

    def _ensure_result(self, task: TaskRecord) -> TaskResult:
        if task.result is None:
            task.result = self._blank_result(task)
        return task.result

    def _append_task_message(
        self,
        task: TaskRecord,
        role: str,
        content: str,
        *,
        replan: bool = False,
    ) -> TaskMessage:
        result = self._ensure_result(task)
        message = TaskMessage(
            id=f"{task.id}-msg-{len(result.messages) + 1}",
            role=role,  # type: ignore[arg-type]
            content=content,
            created_at=_utcnow(),
            replan=replan,
        )
        result.messages.append(message)
        return message

    def _append_progress_message(self, task: TaskRecord, content: str) -> None:
        self._append_task_message(task, "system", content)
        task_service.save_task_record(task)

    def _activate_runtime(self, handle: _AssistantRuntimeHandle) -> None:
        handle.assistant.activate_runtime(handle.thread_id)

    def _build_runtime_sync(
        self,
        task: TaskRecord,
        *,
        allow_local_fallback: bool = False,
        restore_existing_session: bool = True,
    ) -> _AssistantRuntimeHandle:
        _load_runtime_env()
        self._append_progress_message(task, "正在加载运行环境配置。")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            checked_paths = ", ".join(str(path) for path in ENV_FILES)
            raise RuntimeError(
                "缺少 OPENAI_API_KEY，无法启动 gitIssueAssitant。"
                f" 已检查进程环境变量以及 {checked_paths}。"
                " .env.example 不会被自动加载。"
            )

        self._append_progress_message(task, "正在初始化模型与 Agent。")
        enabled_skills = (
            task.config.enabled_skills
            if task.config.enabled_skills is not None
            else skill_service.default_enabled_names()
        )
        enabled_skill_set = {name.strip() for name in enabled_skills if name.strip()}
        sandbox_manager = self._get_sandbox_manager(SandboxManager)
        # 用户明确选择本地回退时，强制禁用 Docker 沙箱，避免重复尝试启动容器
        if allow_local_fallback and sandbox_manager is not None:
            sandbox_manager.stop_all()
            self._sandbox_manager = None
            sandbox_manager = None
            self._append_progress_message(task, "用户已选择本地执行，Docker 沙箱已禁用，使用本地执行环境。")
        elif sandbox_manager is None:
            self._append_progress_message(task, "Docker 沙箱已禁用，当前任务将使用本地执行环境。")
        else:
            self._append_progress_message(
                task,
                "准备启用 Docker 沙箱。后续会复制仓库、检查或拉取镜像、启动容器并执行 .agent-sandbox.yml 中的安装命令。",
            )
        assistant = IssueAssistantService.create_for_rest_runtime(
            workspace_root=self.workspace_root,
            enabled_skill_names=enabled_skill_set,
            sandbox_manager=sandbox_manager,
            model_name=task.config.model_name,
        )
        session_service = assistant.session_service
        session_service.repos_root = _configured_clone_root()

        restored_session = None
        if restore_existing_session and task.thread_id:
            try:
                restored_session = session_service.switch_session_by_thread_id(task.thread_id)
                self._append_progress_message(
                    task,
                    f"已恢复历史会话：session_id={restored_session.session_id}, thread_id={restored_session.thread_id}",
                )
            except ValueError:
                restored_session = None

        if restored_session is None:
            self._append_progress_message(task, "正在准备仓库：clone 远程仓库或复用本地仓库目录。")
            session_service.create_session(
                task.config.repo_source,
                target_dir=task.config.target_dir,
                force=True,
            )
            self._append_progress_message(task, f"仓库已准备：{session_service.current_repo}")
            if sandbox_manager is not None:
                self._append_progress_message(task, "正在启动 Docker 沙箱，请等待镜像拉取、容器启动和依赖安装完成。")
            session_service.set_issue(task.config.issue_input)

        thread_id = session_service.get_current_thread_id()
        initial_state = assistant.graph_state(thread_id)
        if restored_session is not None and not initial_state:
            self._append_progress_message(task, "历史会话缺少 graph state，正在重新初始化任务上下文。")
            session_service.set_issue(task.config.issue_input)
            initial_state = assistant.graph_state(thread_id)
        # 本地回退时，如果恢复的 session 处于 SANDBOX_UNAVAILABLE 状态，需要重新初始化
        if allow_local_fallback and restored_session is not None and initial_state.get("status") == SANDBOX_UNAVAILABLE_STATUS:
            self._append_progress_message(task, "正在重新初始化任务为本地执行模式。")
            session_service.set_issue(task.config.issue_input)
            initial_state = assistant.graph_state(thread_id)
        sandbox_id = str(initial_state.get("sandbox_id") or "")
        session = session_service._current_session()
        sandbox_error = getattr(session, "sandbox_error", "") if session is not None else ""
        if sandbox_id:
            self._append_progress_message(task, f"Docker 沙箱已就绪：sandbox_id={sandbox_id}，执行目录为 {session_service.current_repo}")
        elif sandbox_manager is not None and sandbox_error and not allow_local_fallback:
            detail = f"详细原因：{sandbox_error}" if sandbox_error else "未获取到详细原因。"
            self._append_progress_message(task, f"Docker 沙箱不可用，已暂停任务。请选择在本地执行或终止任务。{detail}")
            initial_state = assistant.update_graph_state(
                thread_id,
                {"status": SANDBOX_UNAVAILABLE_STATUS},
            )
        elif sandbox_manager is not None and sandbox_error:
            detail = f"详细原因：{sandbox_error}" if sandbox_error else "未获取到详细原因。"
            self._append_progress_message(task, f"用户已选择本地执行，Docker 沙箱不可用，继续使用本地执行环境。{detail}")
        elif sandbox_manager is not None:
            self._append_progress_message(task, "Docker 沙箱未启用成功，已按配置回退到本地执行环境。未获取到详细原因。")
        else:
            self._append_progress_message(task, "本地执行环境已就绪。")

        return _AssistantRuntimeHandle(
            assistant=assistant,
            thread_id=thread_id,
            initial_state=initial_state,
            sandbox_error=str(sandbox_error or ""),
        )

    async def _ensure_runtime(
        self,
        task: TaskRecord,
        *,
        reset: bool,
        allow_local_fallback: bool = False,
    ) -> _AssistantRuntimeHandle:
        # 本地回退时需要强制重建 runtime（禁用沙箱、重置 graph state）
        needs_rebuild = reset or allow_local_fallback or task.id not in self._runtime_handles or task.status in TERMINAL_TASK_STATUSES
        if needs_rebuild:
            previous_handle = self._runtime_handles.pop(task.id, None)
            if previous_handle is not None:
                try:
                    previous_handle.assistant.cleanup_current_session()
                except Exception:
                    pass  # 清理失败不阻塞重建流程
            # 本地回退时优先复用已有 session，避免重建后再次尝试 Docker
            restore_session = allow_local_fallback or not reset
            handle = await asyncio.to_thread(
                self._build_runtime_sync,
                task,
                allow_local_fallback=allow_local_fallback,
                restore_existing_session=restore_session,
            )
            self._runtime_handles[task.id] = handle
            task.thread_id = handle.thread_id
            task.repo_path = handle.assistant.current_repo
            result = self._ensure_result(task)
            if handle.initial_state:
                result.current_state = self._state_snapshot(task, handle.initial_state)
            result.summary = "任务上下文已初始化，等待执行。"
            result.error_message = None
            task.result = result
            task.status = "scheduled"
            task.started_at = None
            task.finished_at = None
            task_service.save_task_record(task)
            return handle

        handle = self._runtime_handles[task.id]
        self._activate_runtime(handle)
        return handle

    def _state_snapshot(self, task: TaskRecord, state: dict[str, Any]) -> RuntimeSnapshot:
        messages = state.get("messages") or []
        last_message = ""
        if messages:
            last_message = _serialize_content(
                getattr(messages[-1], "content", ""))

        return RuntimeSnapshot(
            thread_id=task.thread_id,
            repo_path=state.get("repo_path") or task.repo_path,
            issue_description=state.get(
                "issue_description") or task.config.issue_input,
            status=str(state.get("status") or "INIT"),
            iteration_count=int(state.get("iteration_count") or 0),
            plan=[str(item) for item in (state.get("plan") or [])],
            reflexion_notes=str(state.get("reflexion_notes") or ""),
            last_message=last_message,
            sandbox_id=str(state.get("sandbox_id") or ""),
        )

    def _map_task_status(self, runtime_status: str) -> str:
        if runtime_status == "SUCCESS":
            return "completed"
        if runtime_status == "FAILED":
            return "failed"
        if runtime_status == SANDBOX_UNAVAILABLE_STATUS:
            return "scheduled"
        if runtime_status == "INIT":
            return "scheduled"
        return "running"

    def _append_timeline_entries(
        self,
        task: TaskRecord,
        node_name: str,
        payload: dict[str, Any],
    ) -> None:
        result = self._ensure_result(task)
        created_at = _utcnow()

        def next_id() -> str:
            return f"{task.id}-event-{len(result.timeline) + 1}"

        if node_name in {"h_planner", "planner"}:
            goals = payload.get("goals") or payload.get("plan") or []
            plan_content = "\n".join(
                str(item.get("description", item)) if isinstance(item, dict) else str(item)
                for item in goals
                if item
            )
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
            content = _serialize_content(getattr(ai_message, "content", ""))
            result.timeline.append(
                TimelineEntry(
                    id=next_id(),
                    node="react",
                    event_type="assistant",
                    title="Agent 思考",
                    content=content,
                    tool_calls=_to_tool_call_records(tool_calls),
                    created_at=created_at,
                )
            )
            display_content = _strip_agent_control_lines(content)
            if display_content:
                self._append_task_message(task, "assistant", display_content)
            elif tool_calls:
                tool_names = ", ".join(
                    str(tool_call.get("name", "tool")) for tool_call in tool_calls[:3]
                )
                suffix = "..." if len(tool_calls) > 3 else ""
                self._append_task_message(task, "assistant", f"正在调用工具：{tool_names}{suffix}")
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
                tool_name = getattr(message, "name", None) or getattr(
                    message, "tool_call_id", None) or "tool"
                result.timeline.append(
                    TimelineEntry(
                        id=next_id(),
                        node="tools",
                        event_type="tool",
                        title=f"工具输出：{tool_name}",
                        content=_serialize_content(
                            getattr(message, "content", "")),
                        created_at=created_at,
                    )
                )

    def _tool_usage_from_result(self, result: TaskResult) -> list[ToolUsageItem]:
        counter: Counter[str] = Counter()
        for entry in result.timeline:
            for tool_call in entry.tool_calls:
                counter[tool_call.name] += 1

        return [
            ToolUsageItem(name=name, count=count)
            for name, count in counter.most_common()
        ]

    def _latest_timeline_content(self, result: TaskResult, event_type: str) -> str:
        for entry in reversed(result.timeline):
            if entry.event_type == event_type and entry.content.strip():
                return entry.content.strip()
        return ""

    def _test_summary(self, result: TaskResult) -> tuple[str, str]:
        test_entries = [
            entry
            for entry in result.timeline
            if entry.event_type == "tool" and "run_pytest" in entry.title
        ]
        if not test_entries:
            return "未检测到测试命令", "未检测到测试输出"
        output = test_entries[-1].content.strip() or "无输出"
        return "run_pytest", output

    def _build_fix_report(self, task: TaskRecord, result: TaskResult) -> FixReport | None:
        if task.status != "completed":
            return None
        repo_path = task.repo_path or (
            result.current_state.repo_path if result.current_state else "")
        diff = ""
        if repo_path:
            try:
                diff = IssueAssistantService.get_repository_diff(repo_path).diff
            except Exception:
                diff = ""

        test_command, test_output = self._test_summary(result)
        root_cause = self._latest_timeline_content(
            result, "reflection") or self._latest_timeline_content(result, "assistant")
        suggested_title = f"fix: {task.name}"
        markdown, pr_title, pr_body = IssueAssistantService.build_fix_report_from_context(
            report_title=f"Agent 修复报告 - {task.name}",
            issue_description=task.config.issue_input,
            diff=diff,
            root_cause=root_cause,
            test_command=test_command,
            test_output=test_output,
            commit_plan={"message": suggested_title},
        )
        return FixReport(
            file_name=f"{task.id}-fix-report.md",
            markdown=markdown,
            suggested_pr_title=pr_title,
            suggested_pr_description=pr_body,
            created_at=_utcnow(),
        )

    def _build_metrics(
        self,
        task: TaskRecord,
        result: TaskResult,
    ) -> list[MetricScore]:
        snapshot = result.current_state or RuntimeSnapshot()
        tool_usage = {item.name: item.count for item in result.tool_usage}
        duration_seconds = 0.0
        if task.started_at:
            end_time = task.finished_at or _utcnow()
            duration_seconds = max(
                (end_time - task.started_at).total_seconds(), 0.0)

        return [
            MetricScore(
                name="success",
                value=1.0 if task.status == "completed" else 0.0,
                category="结果",
                unit=None,
                description="1 表示成功，0 表示暂未成功。",
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
                value=float(sum(tool_usage.get(name, 0)
                            for name in EDIT_TOOL_NAMES)),
                category="工具",
                unit="次",
                description="代码修改相关工具调用次数。",
            ),
            MetricScore(
                name="test_run_count",
                value=float(sum(tool_usage.get(name, 0)
                            for name in TEST_TOOL_NAMES)),
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

    def _refresh_result(self, task: TaskRecord) -> None:
        result = self._ensure_result(task)
        result.tool_usage = self._tool_usage_from_result(result)
        result.metrics = self._build_metrics(task, result)
        result.logs_preview = [
            f"{entry.created_at.strftime('%H:%M:%S')} {entry.title}: "
            f"{(entry.content.splitlines()[0] if entry.content else '无输出')}"
            for entry in result.timeline
        ]

        if task.status == "completed":
            result.outcome = "completed"
            result.summary = (
                f"任务执行完成，仓库已定位到 {task.repo_path or task.config.repo_source}，"
                f"共执行 {result.current_state.iteration_count if result.current_state else 0} 轮。"
            )
            if result.fix_report is None:
                result.fix_report = self._build_fix_report(task, result)
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
        self._refresh_agent_trace(task)

    def _refresh_agent_trace(
        self,
        task: TaskRecord,
        state: dict[str, Any] | None = None,
    ) -> None:
        result = self._ensure_result(task)
        if state is None and task.id in self._runtime_handles:
            handle = self._runtime_handles[task.id]
            try:
                state = handle.assistant.graph_state(handle.thread_id)
            except Exception:
                state = None
        result.agent_trace = agent_trace_service.build_trace(task, result, state or {})

    def _sync_state(self, task: TaskRecord, state: dict[str, Any]) -> None:
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
        self._refresh_agent_trace(task, state)

    def _mark_failed(self, task: TaskRecord, error_message: str) -> None:
        result = self._ensure_result(task)
        task.status = "failed"
        task.finished_at = _utcnow()
        result.error_message = error_message
        result.current_state = result.current_state or RuntimeSnapshot(
            thread_id=task.thread_id,
            repo_path=task.repo_path,
            issue_description=task.config.issue_input,
            status="FAILED",
        )
        result.current_state.status = "FAILED"
        self._refresh_result(task)
        self._refresh_agent_trace(task)
        task_service.save_task_record(task)

    def _clear_previous_failure(self, task: TaskRecord) -> None:
        result = self._ensure_result(task)
        result.error_message = None
        task.finished_at = None

    def _acknowledge_local_fallback(self, task: TaskRecord) -> None:
        result = self._ensure_result(task)
        snapshot = result.current_state
        if snapshot is None or snapshot.status != SANDBOX_UNAVAILABLE_STATUS:
            return

        snapshot.status = "INIT"
        snapshot.sandbox_id = ""
        self._append_task_message(task, "system", "已选择本地执行，正在重新初始化任务。")

    async def _run_graph(
        self,
        task: TaskRecord,
        handle: _AssistantRuntimeHandle,
        *,
        mode: str,
    ) -> None:
        self._activate_runtime(handle)
        task.status = "running"
        task.started_at = task.started_at or _utcnow()
        self._clear_previous_failure(task)
        self._refresh_result(task)
        task_service.save_task_record(task)

        async for event in handle.assistant.stream_graph_updates(handle.thread_id):
            node_name = next(iter(event))
            self._append_timeline_entries(
                task, node_name, event[node_name])
            state = handle.assistant.graph_state(handle.thread_id)
            handle.assistant.persist_state(handle.thread_id, node_name)
            self._sync_state(task, state)
            task_service.save_task_record(task)

        final_state = handle.assistant.graph_state(handle.thread_id)
        handle.assistant.persist_state(handle.thread_id)
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
                handle = await self._ensure_runtime(
                    task,
                    reset=request.reset,
                    allow_local_fallback=request.allow_local_fallback,
                )
                if handle.sandbox_error and not request.allow_local_fallback:
                    task.status = "scheduled"
                    self._refresh_result(task)
                    task_service.save_task_record(task)
                    return
                await self._run_graph(task, handle, mode=request.mode or task.config.run_mode)
            except Exception as exc:
                self._mark_failed(task, str(exc))
            finally:
                job = self._background_jobs.get(task_id)
                if job is not None and job.done():
                    self._background_jobs.pop(task_id, None)

    async def run(self, task_id: str, request: TaskRunRequest) -> TaskRecord:
        task = task_service.get_task_record(task_id)
        if task is None:
            raise ValueError("Task not found")

        self._prune_finished_background_job(task_id)
        job = self._background_jobs.get(task_id)
        if job is not None and not job.done():
            return task

        request_mode = request.mode or task.config.run_mode
        run_request = TaskRunRequest(
            mode=request_mode,
            reset=request.reset,
            allow_local_fallback=request.allow_local_fallback,
        )

        if request_mode == "auto":
            for task_key in list(self._background_jobs.keys()):
                self._prune_finished_background_job(task_key)
            if any(not background_job.done() for task_key, background_job in self._background_jobs.items() if task_key != task_id):
                raise RuntimeError("当前已有其他任务在运行，gitIssueAssitant 运行时暂不支持并发执行。")

            if run_request.allow_local_fallback:
                self._acknowledge_local_fallback(task)
            task.status = "scheduled"
            self._refresh_result(task)
            task_service.save_task_record(task)
            self._track_background_job(
                task_id,
                asyncio.create_task(self._execute(task_id, run_request)),
            )
            return task

        await self._execute(task_id, run_request)
        latest_task = task_service.get_task_record(task_id)
        if latest_task is None:
            raise ValueError("Task not found")
        return latest_task

    def get_result(self, task_id: str) -> TaskResult | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        self._refresh_result(task)
        task_service.save_task_record(task)
        return self._ensure_result(task)

    def get_trace(self, task_id: str) -> AgentTrace | None:
        result = self.get_result(task_id)
        if result is None:
            return None
        return result.agent_trace

    def get_messages(self, task_id: str) -> TaskMessageList | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        result = self._ensure_result(task)
        return TaskMessageList(task_id=task.id, messages=result.messages)

    def submit_message(self, task_id: str, payload: TaskMessageCreate) -> TaskMessageList | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        content = payload.content.strip()
        if not content:
            raise ValueError("Message content cannot be empty")

        self._prune_finished_background_job(task_id)
        handle = self._runtime_handles.get(task_id)
        if handle is None:
            snapshot = task.result.current_state if task.result else None
            allow_local_fallback = bool(task.repo_path and snapshot and not snapshot.sandbox_id)
            handle = self._build_runtime_sync(
                task,
                allow_local_fallback=allow_local_fallback,
                restore_existing_session=True,
            )
            self._runtime_handles[task_id] = handle
            task.thread_id = handle.thread_id
            task.repo_path = handle.assistant.current_repo
            if handle.initial_state:
                self._ensure_result(task).current_state = self._state_snapshot(task, handle.initial_state)

        self._activate_runtime(handle)
        self._append_task_message(task, "user", content, replan=payload.replan)
        handle.assistant.inject_message(handle.thread_id, content, replan=payload.replan)

        current_state = handle.assistant.graph_state(handle.thread_id)
        if current_state.get("status") in ("SUCCESS", "FAILED"):
            handle.assistant.reopen_after_terminal(handle.thread_id)
            current_state = handle.assistant.graph_state(handle.thread_id)
            self._append_task_message(
                task,
                "system",
                "已接收追加要求，任务已重新打开并将继续自动执行。",
                replan=payload.replan,
            )
            task.status = "scheduled"
            self._clear_previous_failure(task)

        self._sync_state(task, current_state)
        handle.assistant.persist_state(handle.thread_id)
        if task.status == "running":
            task.status = "scheduled"
            self._refresh_result(task)
        task_service.save_task_record(task)
        return self.get_messages(task_id)

    def clear_task_state(self, task_id: str) -> None:
        job = self._background_jobs.pop(task_id, None)
        if job is not None and not job.done():
            job.cancel()
        handle = self._runtime_handles.pop(task_id, None)
        if handle is not None:
            handle.assistant.cleanup_current_session()

    def shutdown(self) -> None:
        for task_id in list(self._runtime_handles.keys()):
            self.clear_task_state(task_id)
        if self._sandbox_manager is not None:
            self._sandbox_manager.stop_all()
            self._sandbox_manager = None

    def recover_interrupted_tasks(self) -> int:
        recovered_count = 0
        for task in task_service.list_task_records():
            if task.status not in {"scheduled", "running"}:
                continue

            result = self._ensure_result(task)
            snapshot = result.current_state
            if snapshot and snapshot.status == SANDBOX_UNAVAILABLE_STATUS:
                continue

            self._append_task_message(
                task,
                "system",
                "后端服务在任务执行过程中重启，原后台执行已中断。请重新运行任务继续。",
            )
            self._mark_failed(task, "后端服务重启，后台执行已中断。请重新运行任务继续。")
            recovered_count += 1

        return recovered_count

    def terminate_after_sandbox_unavailable(self, task_id: str) -> TaskRecord | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        self.clear_task_state(task_id)
        self._append_task_message(task, "system", "用户选择终止任务：Docker 沙箱不可用，未继续本地执行。")
        self._mark_failed(task, "用户选择终止任务：Docker 沙箱不可用，未继续本地执行。")
        return task

    def _repo_path_for_task(self, task: TaskRecord) -> Path:
        repo_path = task.repo_path
        if not repo_path and task.result and task.result.current_state:
            repo_path = task.result.current_state.repo_path
        if not repo_path:
            raise ValueError("Task has no local repository path")
        return IssueAssistantService.resolve_git_repo(repo_path)

    def get_git_diff(self, task_id: str) -> GitDiffResponse | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None

        diff_result = IssueAssistantService.get_repository_diff(self._repo_path_for_task(task))

        return GitDiffResponse(
            task_id=task.id,
            repo_path=diff_result.repo_path,
            branch=diff_result.branch,
            status=diff_result.status,
            diff=diff_result.diff,
            has_changes=diff_result.has_changes,
        )

    def get_fix_report(self, task_id: str) -> FixReport | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        result = self.get_result(task_id)
        if result is None:
            return None
        if result.fix_report is None:
            result.fix_report = self._build_fix_report(task, result)
            task_service.save_task_record(task)
        return result.fix_report

    def push_changes(self, task_id: str, request: GitPushRequest) -> GitPushResponse | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        if task.status != "completed":
            raise ValueError("Only completed tasks can be pushed")

        commit_message = (
            request.commit_message.strip()
            if request.commit_message and request.commit_message.strip()
            else f"fix: {task.name}"
        )
        push_result = IssueAssistantService.push_repository_changes(
            repo_path=self._repo_path_for_task(task),
            commit_message=commit_message,
            remote=request.remote,
            branch=request.branch,
        )

        result = self._ensure_result(task)
        result.last_commit_hash = push_result.commit_hash
        task_service.save_task_record(task)
        return GitPushResponse(
            task_id=task.id,
            repo_path=push_result.repo_path,
            commit_hash=push_result.commit_hash,
            pushed=push_result.pushed,
            output=push_result.output,
        )

    def create_pull_request(
        self,
        task_id: str,
        request: GitPullRequestRequest,
    ) -> GitPullRequestResponse | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        if task.status != "completed":
            raise ValueError("Only completed tasks can create pull requests")

        remote = request.remote.strip() or "origin"
        branch = request.branch.strip(
        ) if request.branch and request.branch.strip() else f"agent-fix-{task.id}"
        commit_message = request.commit_message.strip(
        ) if request.commit_message and request.commit_message.strip() else f"fix: {task.name}"
        report = self.get_fix_report(task_id)
        title = request.title.strip() if request.title and request.title.strip() else (
            report.suggested_pr_title if report else f"fix: {task.name}")
        body = request.body.strip() if request.body and request.body.strip() else (
            report.suggested_pr_description if report else "")

        pr_result = IssueAssistantService.create_repository_pull_request(
            repo_path=self._repo_path_for_task(task),
            commit_message=commit_message,
            title=title,
            body=body,
            branch=branch,
            base_branch=request.base_branch,
            remote=remote,
        )
        result = self._ensure_result(task)
        result.last_commit_hash = pr_result.commit_hash
        result.pull_request_url = pr_result.pr_url
        task_service.save_task_record(task)
        return GitPullRequestResponse(
            task_id=task.id,
            repo_path=pr_result.repo_path,
            branch=pr_result.branch,
            base_branch=pr_result.base_branch,
            commit_hash=pr_result.commit_hash,
            pr_url=result.pull_request_url,
            output=pr_result.output,
        )

    def compare(self, task_ids: list[str]) -> ComparisonResponse:
        tasks = task_service.list_tasks()
        selected_ids = set(task_ids) if task_ids else {
            task.id for task in tasks}
        items: list[ComparisonItem] = []
        compared_metric_names: list[str] = []

        for task_response in tasks:
            if task_response.id not in selected_ids:
                continue
            result = task_response.result or self.get_result(task_response.id)
            if result is None:
                continue
            compared_metric_names.extend(
                metric.name for metric in result.metrics)
            items.append(
                ComparisonItem(
                    task_id=task_response.id,
                    task_name=task_response.name,
                    status=task_response.status,
                    summary=result.summary,
                    scores=result.metrics,
                )
            )

        def metric(item: ComparisonItem, name: str) -> float:
            for score in item.scores:
                if score.name == name:
                    return score.value
            return 0.0

        count = len(items)
        aggregate = ComparisonAggregate()
        if count:
            aggregate = ComparisonAggregate(
                success_rate=sum(metric(item, "success") for item in items) / count,
                failed_count=sum(1 for item in items if item.status == "failed"),
                average_duration_seconds=sum(metric(item, "duration_seconds") for item in items) / count,
                average_tool_call_count=sum(metric(item, "tool_call_count") for item in items) / count,
                average_test_run_count=sum(metric(item, "test_run_count") for item in items) / count,
            )

        return ComparisonResponse(
            compared_metrics=sorted(set(compared_metric_names)),
            items=items,
            aggregate=aggregate,
        )

    def export_report_markdown(
        self,
        task_ids: list[str],
    ) -> str:
        comparison = self.compare(task_ids)
        lines = [
            "# Agent 评测对比报告",
            "",
            "## 总体指标",
            f"- 成功率: {comparison.aggregate.success_rate:.2%}",
            f"- 失败数: {comparison.aggregate.failed_count}",
            f"- 平均耗时: {comparison.aggregate.average_duration_seconds:.2f} 秒",
            f"- 平均工具调用: {comparison.aggregate.average_tool_call_count:.2f} 次",
            f"- 平均测试次数: {comparison.aggregate.average_test_run_count:.2f} 次",
            "",
            "## 任务对比",
            "| 任务 | 状态 | success | iteration_count | tool_call_count | test_run_count | duration_seconds |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]

        def score_value(item: ComparisonItem, name: str) -> float:
            for score in item.scores:
                if score.name == name:
                    return score.value
            return 0.0

        for item in comparison.items:
            lines.append(
                "| "
                f"{item.task_name} | {item.status} | "
                f"{score_value(item, 'success'):.2f} | "
                f"{score_value(item, 'iteration_count'):.2f} | "
                f"{score_value(item, 'tool_call_count'):.2f} | "
                f"{score_value(item, 'test_run_count'):.2f} | "
                f"{score_value(item, 'duration_seconds'):.2f} |"
            )

        return "\n".join(lines)

    def export_report_csv(
        self,
        task_ids: list[str],
    ) -> str:
        import csv
        from io import StringIO

        comparison = self.compare(task_ids)
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "type",
                "id",
                "name",
                "status",
                "success",
                "iteration_count",
                "tool_call_count",
                "test_run_count",
                "duration_seconds",
                "summary",
            ]
        )

        def item_score(item: ComparisonItem, name: str) -> float:
            for score in item.scores:
                if score.name == name:
                    return score.value
            return 0.0

        for item in comparison.items:
            writer.writerow(
                [
                    "task",
                    item.task_id,
                    item.task_name,
                    item.status,
                    item_score(item, "success"),
                    item_score(item, "iteration_count"),
                    item_score(item, "tool_call_count"),
                    item_score(item, "test_run_count"),
                    item_score(item, "duration_seconds"),
                    item.summary,
                ]
            )

        return output.getvalue()




