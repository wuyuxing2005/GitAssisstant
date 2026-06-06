from __future__ import annotations

import subprocess
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.task import EvaluationTaskRecord
from app.schemas.task import (
    AgentTrace,
    AgentTraceRepoInfo,
    EvaluationResult,
    TraceEvent,
    ToolCallInfo,
)
from app.utils.time import now_local


TRACE_SCHEMA_VERSION = "agent-trace-v1"
AGENT_VERSION = "agent-v3"
MAX_PREVIEW_CHARS = 4000


def _shorten(value: Any, limit: int = MAX_PREVIEW_CHARS) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."


def _git_output(repo_path: str | None, args: list[str]) -> str:
    if not repo_path:
        return ""
    path = Path(repo_path)
    if not path.exists():
        return ""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _trace_status(task_status: str, runtime_status: str = "") -> str:
    if task_status == "completed" or runtime_status == "SUCCESS":
        return "success"
    if task_status == "failed" or runtime_status == "FAILED":
        return "failed"
    if runtime_status == "SANDBOX_UNAVAILABLE":
        return "waiting_confirmation"
    if task_status == "draft":
        return "running"
    return "running"


def _timeline_event_type(node: str, event_type: str) -> tuple[str, str, str]:
    if node in {"h_planner", "planner"} or event_type == "plan":
        return "planning", "planning", "agent"
    if node == "react" or event_type == "assistant":
        return "llm_generation", "react", "agent"
    if node == "reflect" or event_type == "reflection":
        return "reflection", "reflection", "agent"
    if node == "tools" or event_type == "tool":
        return "tool_result", "tool_execution", "tool"
    if node.startswith("finish"):
        return "verify", "verify", "agent"
    return event_type or "llm_generation", node or "runtime", "agent"


def _event_status(task_status: str, event_type: str, content: str) -> str:
    lowered = content.lower()
    if event_type == "tool_result" and (lowered.startswith("error:") or "拒绝执行" in content):
        return "failed"
    if event_type == "verify" and task_status == "failed":
        return "failed"
    if event_type == "patch_proposal":
        return "waiting_confirmation"
    return "success"


def _tool_result_status(status: str) -> str:
    if status == "success":
        return "success"
    if status == "rejected":
        return "failed"
    return "failed" if status else "success"


def _duration_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    if not started_at:
        return None
    end = ended_at or now_local()
    return max(int((end - started_at).total_seconds() * 1000), 0)


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class AgentTraceService:
    def build_trace(
        self,
        task: EvaluationTaskRecord,
        result: EvaluationResult,
        state: dict[str, Any] | None = None,
    ) -> AgentTrace:
        state = state or {}
        snapshot = result.current_state
        runtime_status = str(state.get("status") or (snapshot.status if snapshot else ""))
        sandbox_id = str(
            state.get("sandbox_id")
            or (snapshot.sandbox_id if snapshot else "")
            or ""
        )
        repo_path = str(
            state.get("repo_path")
            or task.repo_path
            or (snapshot.repo_path if snapshot else "")
            or ""
        )
        started_at = task.started_at or result.started_at
        ended_at = task.finished_at or result.finished_at

        events: list[TraceEvent] = []
        pending_tool_calls: dict[str, deque[str]] = defaultdict(deque)

        def append_event(
            *,
            timestamp: datetime | None,
            event_type: str,
            phase: str,
            actor: str,
            status: str,
            title: str,
            content: str = "",
            parent_event_id: str | None = None,
            duration_ms: int | None = None,
            tool_call: ToolCallInfo | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> TraceEvent:
            event = TraceEvent(
                event_id=f"{task.id}-trace-event-{len(events) + 1}",
                seq=len(events) + 1,
                parent_event_id=parent_event_id,
                timestamp=timestamp or now_local(),
                event_type=event_type,
                phase=phase,
                actor=actor,
                status=status,
                title=title,
                content=_shorten(content),
                duration_ms=duration_ms,
                tool_call=tool_call,
                metadata=metadata or {},
            )
            events.append(event)
            return event

        append_event(
            timestamp=task.created_at,
            event_type="user_input",
            phase="conversation",
            actor="user",
            status="success",
            title="任务输入",
            content=task.config.issue_input,
            metadata={"task_name": task.name, "description": task.description},
        )

        for message in result.messages:
            if message.role == "assistant":
                continue
            if message.content == task.config.issue_input:
                continue
            event_type = "user_input" if message.role == "user" else "llm_generation"
            append_event(
                timestamp=message.created_at,
                event_type=event_type,
                phase="conversation",
                actor=message.role,
                status="success",
                title="用户补充要求" if message.role == "user" else "系统进度",
                content=message.content,
                metadata={"replan": message.replan},
            )

        selected_skill = str(state.get("selected_skill") or "")
        if selected_skill:
            append_event(
                timestamp=started_at,
                event_type="skill_select",
                phase="skill_selection",
                actor="agent",
                status="success",
                title="选择 Skill",
                content=f"selected_skill={selected_skill}",
                metadata={
                    "priority_tools": state.get("skill_priority_tools") or [],
                    "allowed_tools": state.get("skill_allowed_tools") or [],
                },
            )

        raw_tool_events = list(state.get("tool_call_events") or [])
        has_rich_tool_events = bool(raw_tool_events)

        for entry in result.timeline:
            event_type, phase, actor = _timeline_event_type(entry.node, entry.event_type)
            if event_type == "tool_result" and has_rich_tool_events:
                continue

            event = append_event(
                timestamp=entry.created_at,
                event_type=event_type,
                phase=phase,
                actor=actor,
                status=_event_status(task.status, event_type, entry.content),
                title=entry.title,
                content=entry.content,
                metadata={"timeline_id": entry.id, "node": entry.node},
            )

            for tool_call in entry.tool_calls:
                call_event = append_event(
                    timestamp=entry.created_at,
                    event_type="tool_call",
                    phase="tool_execution",
                    actor="agent",
                    status="success",
                    title=f"发起工具调用：{tool_call.name}",
                    content="",
                    parent_event_id=event.event_id,
                    tool_call=ToolCallInfo(
                        name=tool_call.name,
                        arguments=tool_call.args,
                    ),
                )
                pending_tool_calls[tool_call.name].append(call_event.event_id)

        for raw_event in raw_tool_events:
            tool_name = str(raw_event.get("tool_name") or "unknown_tool")
            parent_event_id = (
                pending_tool_calls[tool_name].popleft()
                if pending_tool_calls.get(tool_name)
                else None
            )
            append_event(
                timestamp=_parse_timestamp(raw_event.get("timestamp")),
                event_type="tool_result",
                phase="tool_execution",
                actor="tool",
                status=_tool_result_status(str(raw_event.get("status") or "")),
                title=f"工具输出：{tool_name}",
                content=str(raw_event.get("result_preview") or raw_event.get("error_message") or ""),
                parent_event_id=parent_event_id,
                duration_ms=int(raw_event.get("latency_ms") or 0),
                tool_call=ToolCallInfo(
                    name=tool_name,
                    arguments=dict(raw_event.get("arguments") or {}),
                    result_preview=str(raw_event.get("result_preview") or ""),
                    error_message=str(raw_event.get("error_message") or ""),
                    exit_code=raw_event.get("exit_code"),
                    latency_ms=int(raw_event.get("latency_ms") or 0),
                    sandbox_id=str(raw_event.get("sandbox_id") or sandbox_id),
                    affected_files=list(raw_event.get("affected_files") or []),
                ),
                metadata={"raw_tool_status": raw_event.get("status") or ""},
            )

        if task.status in {"completed", "failed"}:
            append_event(
                timestamp=ended_at,
                event_type="verify",
                phase="verify",
                actor="agent",
                status="success" if task.status == "completed" else "failed",
                title="最终状态判定",
                content=result.summary or result.error_message or "",
                metadata={"runtime_status": runtime_status},
            )

        events.sort(key=lambda event: (event.timestamp, event.seq))
        for index, event in enumerate(events, start=1):
            event.seq = index

        failure_fields = self._failure_fields(task, result, events)
        return AgentTrace(
            schema_version=TRACE_SCHEMA_VERSION,
            trace_id=f"trace-{task.id}",
            task_id=task.id,
            conversation_id=task.thread_id or f"conv-{task.id}",
            issue_id=self._issue_id(task.config.issue_input),
            agent_version=AGENT_VERSION,
            repo=AgentTraceRepoInfo(
                repo_url=_git_output(repo_path, ["config", "--get", "remote.origin.url"])
                or task.config.repo_source,
                branch=_git_output(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]),
                commit=_git_output(repo_path, ["rev-parse", "HEAD"]),
                sandbox_id=sandbox_id,
            ),
            user_input=task.config.issue_input,
            final_response=self._final_response(result),
            status=_trace_status(task.status, runtime_status),
            started_at=started_at,
            ended_at=ended_at,
            total_latency_ms=_duration_ms(started_at, ended_at),
            token_usage=self._token_usage(state),
            events=events,
            **failure_fields,
        )

    def _token_usage(self, state: dict[str, Any]) -> dict[str, int]:
        usage = dict(state.get("token_usage") or {})
        return {
            "prompt": int(usage.get("prompt_tokens") or usage.get("prompt") or 0),
            "completion": int(usage.get("completion_tokens") or usage.get("completion") or 0),
            "total": int(usage.get("total_tokens") or usage.get("total") or 0),
        }

    def _final_response(self, result: EvaluationResult) -> str:
        for message in reversed(result.messages):
            if message.role == "assistant" and message.content.strip():
                return message.content
        return result.summary

    def _issue_id(self, issue_input: str) -> str:
        text = issue_input.strip()
        if "github.com/" not in text:
            return ""
        parts = text.rstrip("/").split("/")
        if len(parts) >= 7 and parts[-2] == "issues":
            return f"github-{parts[-4]}-{parts[-3]}-{parts[-1]}"
        return ""

    def _failure_fields(
        self,
        task: EvaluationTaskRecord,
        result: EvaluationResult,
        events: list[TraceEvent],
    ) -> dict[str, Any]:
        if task.status != "failed":
            return {}
        failed_tool_events = [event for event in events if event.actor == "tool" and event.status == "failed"]
        related_ids = [event.event_id for event in failed_tool_events[-3:]]
        if failed_tool_events:
            return {
                "failure_type": "tool_error",
                "failure_reason": failed_tool_events[-1].tool_call.error_message
                if failed_tool_events[-1].tool_call
                else failed_tool_events[-1].content,
                "related_event_ids": related_ids,
                "suggested_fix": "检查失败工具的参数、输出和沙箱环境后继续运行或调整 Agent 策略。",
            }
        return {
            "failure_type": "agent_reasoning",
            "failure_reason": result.error_message or result.summary or "任务失败，但未检测到明确工具错误。",
            "related_event_ids": [events[-1].event_id] if events else [],
            "suggested_fix": "结合最后一次 Agent 回复、反思事件和验证证据定位失败原因。",
        }


agent_trace_service = AgentTraceService()
