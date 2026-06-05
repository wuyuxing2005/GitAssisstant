from __future__ import annotations
import re
import asyncio
import os
import subprocess
import sys
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.models.task import EvaluationTaskRecord
from app.schemas.task import (
    AgentTrace,
    ComparisonAggregate,
    ComparisonItem,
    ComparisonResponse,
    EvaluationResult,
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
from app.services.skill_service import skill_service
from app.services.task_service import task_service
from app.services.trace_service import agent_trace_service
from app.utils.time import now_local

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
ENV_FILES = (
    WORKSPACE_ROOT / "backend" / ".env",
    WORKSPACE_ROOT / ".env",
)
EDIT_TOOL_NAMES = {"write_file", "replace_in_file", "patch_file"}
TEST_TOOL_NAMES = {"run_pytest"}
TERMINAL_TASK_STATUSES = {"completed", "failed"}
AGENT_DISABLED_GIT_TOOL_NAMES = {"git_add", "git_commit", "git_push"}
MAX_ITERATIONS_REACHED_STATUS = "MAX_ITERATIONS_REACHED"
SANDBOX_UNAVAILABLE_STATUS = "SANDBOX_UNAVAILABLE"


@dataclass
class AssistantRuntimeHandle:
    orchestrator: Any
    manager: Any
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


def _configured_clone_root() -> Path:
    configured = os.getenv("GIT_ISSUE_ASSISTANT_CLONE_ROOT", "").strip()
    if not configured:
        return WORKSPACE_ROOT / "repos"
    clone_root = Path(configured).expanduser()
    if not clone_root.is_absolute():
        clone_root = (WORKSPACE_ROOT / clone_root).resolve()
    clone_root.mkdir(parents=True, exist_ok=True)
    return clone_root


def _run_git_command(
    repo_path: str | Path,
    args: list[str],
    *,
    timeout: int = 120,
    check: bool = True,
) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if check and result.returncode != 0:
        raise RuntimeError(output or f"git {' '.join(args)} failed")
    return output


def _is_git_repo(repo_path: str | Path) -> bool:
    try:
        _run_git_command(
            repo_path, ["rev-parse", "--show-toplevel"], timeout=10)
    except Exception:
        return False
    return True


def _new_file_diff(repo_path: Path, relative_path: str, max_bytes: int = 200_000) -> str:
    file_path = (repo_path / relative_path).resolve()
    try:
        file_path.relative_to(repo_path.resolve())
    except ValueError:
        return ""
    if not file_path.is_file():
        return ""

    data = file_path.read_bytes()
    if b"\0" in data:
        return (
            f"diff --git a/{relative_path} b/{relative_path}\n"
            f"new file mode 100644\n"
            f"Binary files /dev/null and b/{relative_path} differ\n"
        )
    if len(data) > max_bytes:
        return (
            f"diff --git a/{relative_path} b/{relative_path}\n"
            f"new file mode 100644\n"
            f"--- /dev/null\n"
            f"+++ b/{relative_path}\n"
            f"@@\n"
            f"+[new file omitted: {len(data)} bytes]\n"
        )

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    trailing = "\n" if body else ""
    return (
        f"diff --git a/{relative_path} b/{relative_path}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{relative_path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}{trailing}"
    )


def _build_untracked_diff(repo_path: Path) -> str:
    output = _run_git_command(
        repo_path,
        ["ls-files", "--others", "--exclude-standard"],
        timeout=30,
    )
    parts = [
        diff
        for line in output.splitlines()
        if (diff := _new_file_diff(repo_path, line.strip()))
    ]
    return "\n".join(parts)


def _parse_github_remote(remote_url: str) -> tuple[str, str] | None:
    patterns = (
        r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?/?$",
        r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.search(pattern, remote_url.strip())
        if match:
            return match.group("owner"), match.group("repo").removesuffix(".git")
    return None


def _github_json_request(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to create a pull request")

    request = Request(
        f"https://api.github.com{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "gitIssueAssitant",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub PR creation failed: HTTP {exc.code} {detail}") from exc


@lru_cache
def _assistant_components() -> tuple[Any, Any, Any, Any, list[Any], Any, Any, Any]:
    if str(WORKSPACE_ROOT) not in sys.path:
        sys.path.insert(0, str(WORKSPACE_ROOT))

    from gitIssueAssitant.agent import Agent, LLM_factory
    from gitIssueAssitant.orchestrator import AgentOrchestrator
    from gitIssueAssitant.session_manager import SessionManager
    from gitIssueAssitant.tools.sandbox_manager import SandboxManager
    from gitIssueAssitant.tools.tools import AGENT_TOOLS, clear_active_sandbox, set_active_sandbox

    web_safe_tools = [
        tool
        for tool in AGENT_TOOLS
        if getattr(tool, "name", "") not in AGENT_DISABLED_GIT_TOOL_NAMES
    ]

    return Agent, AgentOrchestrator, SessionManager, LLM_factory, web_safe_tools, SandboxManager, clear_active_sandbox, set_active_sandbox


class EvaluationService:
    def __init__(self) -> None:
        self._runtime_handles: dict[str, AssistantRuntimeHandle] = {}
        self._background_jobs: dict[str, asyncio.Task[None]] = {}
        self._execution_lock = asyncio.Lock()
        self._sandbox_manager: Any | None = None

    def _get_sandbox_manager(self, SandboxManager: Any) -> Any | None:
        disabled = os.getenv("GIT_ISSUE_ASSISTANT_DISABLE_SANDBOX", "").lower() in ("1", "true", "yes")
        if disabled:
            if self._sandbox_manager is not None:
                self._sandbox_manager.stop_all()
                self._sandbox_manager = None
            return None
        if self._sandbox_manager is None:
            self._sandbox_manager = SandboxManager(workspace_root=WORKSPACE_ROOT / "workspaces")
        return self._sandbox_manager

    def _blank_result(self, task: EvaluationTaskRecord) -> EvaluationResult:
        return EvaluationResult(
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
                max_iterations=task.config.max_iterations,
            ),
            started_at=task.started_at,
            finished_at=task.finished_at,
        )

    def _ensure_result(self, task: EvaluationTaskRecord) -> EvaluationResult:
        if task.result is None:
            task.result = self._blank_result(task)
        return task.result

    def _append_task_message(
        self,
        task: EvaluationTaskRecord,
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

    def _append_progress_message(self, task: EvaluationTaskRecord, content: str) -> None:
        self._append_task_message(task, "system", content)
        task_service.save_task_record(task)

    def _activate_runtime(self, handle: AssistantRuntimeHandle) -> None:
        _Agent, _AgentOrchestrator, _SessionManager, _LLM_factory, _web_safe_tools, _SandboxManager, clear_active_sandbox, set_active_sandbox = _assistant_components()
        os.environ["GIT_ISSUE_ASSISTANT_HOME"] = str(WORKSPACE_ROOT)
        if handle.manager.current_repo:
            os.environ["GIT_ISSUE_ASSISTANT_REPO_ROOT"] = handle.manager.current_repo
            os.chdir(handle.manager.current_repo)
        clear_active_sandbox()
        config = {"configurable": {"thread_id": handle.thread_id}}
        state = handle.orchestrator.graph.get_state(config).values or {}
        sandbox_id = str(state.get("sandbox_id") or "")
        sandbox = handle.manager.sandbox_manager.get(sandbox_id) if sandbox_id and handle.manager.sandbox_manager else None
        if sandbox is not None and getattr(sandbox, "_started", False):
            set_active_sandbox(sandbox)
            handle.orchestrator._sandbox_activated = True
        else:
            handle.orchestrator._sandbox_activated = False

    def _build_runtime_sync(self, task: EvaluationTaskRecord, *, allow_local_fallback: bool = False) -> AssistantRuntimeHandle:
        _load_runtime_env()
        Agent, AgentOrchestrator, SessionManager, LLM_factory, web_safe_tools, SandboxManager, _clear_active_sandbox, _set_active_sandbox = _assistant_components()
        self._append_progress_message(task, "正在加载运行环境配置。")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            checked_paths = ", ".join(str(path) for path in ENV_FILES)
            raise RuntimeError(
                "缺少 OPENAI_API_KEY，无法启动 gitIssueAssitant。"
                f" 已检查进程环境变量以及 {checked_paths}。"
                " backend/.env.example 不会被自动加载。"
            )

        os.environ["GIT_ISSUE_ASSISTANT_HOME"] = str(WORKSPACE_ROOT)
        original_model_name = os.getenv("MODEL_NAME")
        self._append_progress_message(task, "正在初始化模型与 Agent。")
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
        from gitIssueAssitant.skills import SkillRegistry

        enabled_skills = (
            task.config.enabled_skills
            if task.config.enabled_skills is not None
            else skill_service.default_enabled_names()
        )
        enabled_skill_set = {name.strip() for name in enabled_skills if name.strip()}
        skill_registry = SkillRegistry(WORKSPACE_ROOT / "gitIssueAssitant" / "skills")
        skill_registry.load()
        skill_registry._skills = {
            name: skill
            for name, skill in skill_registry._skills.items()
            if name in enabled_skill_set
        }
        sandbox_manager = self._get_sandbox_manager(SandboxManager)
        if sandbox_manager is None:
            self._append_progress_message(task, "Docker 沙箱已禁用，当前任务将使用本地执行环境。")
        else:
            self._append_progress_message(
                task,
                "准备启用 Docker 沙箱。后续会复制仓库、检查或拉取镜像、启动容器并执行 .agent-sandbox.yml 中的安装命令。",
            )
        orchestrator = AgentOrchestrator(
            agent,
            tools=web_safe_tools,
            skill_registry=skill_registry,
            sandbox_manager=sandbox_manager,
        )
        manager = SessionManager(
            orchestrator,
            workspace_root=WORKSPACE_ROOT,
            sandbox_manager=sandbox_manager,
        )
        manager.repos_root = _configured_clone_root()
        self._append_progress_message(task, "正在准备仓库：clone 远程仓库或复用本地仓库目录。")
        manager.create_session(
            task.config.repo_source,
            target_dir=task.config.target_dir,
            force=True,
        )
        self._append_progress_message(task, f"仓库已准备：{manager.current_repo}")
        if sandbox_manager is not None:
            self._append_progress_message(task, "正在启动 Docker 沙箱，请等待镜像拉取、容器启动和依赖安装完成。")
        manager.set_issue(task.config.issue_input)
        thread_id = manager.get_current_thread_id()
        config = {"configurable": {"thread_id": thread_id}}
        orchestrator.graph.update_state(
            config, {"max_iterations": task.config.max_iterations})
        initial_state = orchestrator.graph.get_state(config).values or {}
        sandbox_id = str(initial_state.get("sandbox_id") or "")
        session = manager._current_session()
        sandbox_error = getattr(session, "sandbox_error", "") if session is not None else ""
        if sandbox_id:
            self._append_progress_message(task, f"Docker 沙箱已就绪：sandbox_id={sandbox_id}，执行目录为 {manager.current_repo}")
        elif sandbox_manager is not None and sandbox_error and not allow_local_fallback:
            detail = f"详细原因：{sandbox_error}" if sandbox_error else "未获取到详细原因。"
            self._append_progress_message(task, f"Docker 沙箱不可用，已暂停任务。请选择在本地执行或终止任务。{detail}")
            orchestrator.graph.update_state(config, {"status": SANDBOX_UNAVAILABLE_STATUS})
            initial_state = orchestrator.graph.get_state(config).values or {}
        elif sandbox_manager is not None and sandbox_error:
            detail = f"详细原因：{sandbox_error}" if sandbox_error else "未获取到详细原因。"
            self._append_progress_message(task, f"用户已选择本地执行，Docker 沙箱不可用，继续使用本地执行环境。{detail}")
        elif sandbox_manager is not None:
            self._append_progress_message(task, "Docker 沙箱未启用成功，已按配置回退到本地执行环境。未获取到详细原因。")
        else:
            self._append_progress_message(task, "本地执行环境已就绪。")

        return AssistantRuntimeHandle(
            orchestrator=orchestrator,
            manager=manager,
            thread_id=thread_id,
            initial_state=initial_state,
            sandbox_error=str(sandbox_error or ""),
        )

    async def _ensure_runtime(
        self,
        task: EvaluationTaskRecord,
        *,
        reset: bool,
        allow_local_fallback: bool = False,
    ) -> AssistantRuntimeHandle:
        needs_rebuild = reset or task.id not in self._runtime_handles or task.status in TERMINAL_TASK_STATUSES
        if needs_rebuild:
            previous_handle = self._runtime_handles.pop(task.id, None)
            if previous_handle is not None:
                previous_handle.manager.cleanup_current_session()
            handle = await asyncio.to_thread(
                self._build_runtime_sync,
                task,
                allow_local_fallback=allow_local_fallback,
            )
            self._runtime_handles[task.id] = handle
            task.thread_id = handle.thread_id
            task.repo_path = handle.manager.current_repo
            result = self._ensure_result(task)
            if handle.initial_state:
                result.current_state = self._state_snapshot(task, handle.initial_state)
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
            last_message = _serialize_content(
                getattr(messages[-1], "content", ""))

        return RuntimeSnapshot(
            thread_id=task.thread_id,
            repo_path=state.get("repo_path") or task.repo_path,
            issue_description=state.get(
                "issue_description") or task.config.issue_input,
            status=str(state.get("status") or "INIT"),
            iteration_count=int(state.get("iteration_count") or 0),
            max_iterations=int(state.get("max_iterations")
                               or task.config.max_iterations),
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
        if runtime_status == MAX_ITERATIONS_REACHED_STATUS:
            return "scheduled"
        if runtime_status == SANDBOX_UNAVAILABLE_STATUS:
            return "scheduled"
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
            if content.strip():
                self._append_task_message(task, "assistant", content)
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

    def _tool_usage_from_result(self, result: EvaluationResult) -> list[ToolUsageItem]:
        counter: Counter[str] = Counter()
        for entry in result.timeline:
            for tool_call in entry.tool_calls:
                counter[tool_call.name] += 1

        return [
            ToolUsageItem(name=name, count=count)
            for name, count in counter.most_common()
        ]

    def _extract_modified_files(self, diff: str) -> list[str]:
        files: list[str] = []
        for line in diff.splitlines():
            if not line.startswith("diff --git a/"):
                continue
            match = re.search(r" b/(.+)$", line)
            if match and match.group(1) not in files:
                files.append(match.group(1))
        return files

    def _latest_timeline_content(self, result: EvaluationResult, event_type: str) -> str:
        for entry in reversed(result.timeline):
            if entry.event_type == event_type and entry.content.strip():
                return entry.content.strip()
        return ""

    def _test_summary(self, result: EvaluationResult) -> tuple[str, str]:
        test_entries = [
            entry
            for entry in result.timeline
            if entry.event_type == "tool" and "run_pytest" in entry.title
        ]
        if not test_entries:
            return "未检测到测试命令", "未检测到测试输出"
        output = test_entries[-1].content.strip() or "无输出"
        return "run_pytest", output

    def _build_fix_report(self, task: EvaluationTaskRecord, result: EvaluationResult) -> FixReport | None:
        if task.status != "completed":
            return None
        repo_path = task.repo_path or (
            result.current_state.repo_path if result.current_state else "")
        diff = ""
        if repo_path:
            try:
                diff_parts = [
                    _run_git_command(
                        repo_path, ["diff", "--no-ext-diff", "--binary"], timeout=60),
                    _run_git_command(
                        repo_path, ["diff", "--no-ext-diff", "--binary", "--cached"], timeout=60),
                    _build_untracked_diff(Path(repo_path)),
                ]
                diff = "\n".join(part for part in diff_parts if part.strip())
            except Exception:
                diff = ""

        files = self._extract_modified_files(diff)
        test_command, test_output = self._test_summary(result)
        root_cause = self._latest_timeline_content(
            result, "reflection") or self._latest_timeline_content(result, "assistant")
        key_changes = "\n".join(
            f"- {path}: 根据 diff 完成针对性修改。" for path in files) or "- 未检测到文件修改。"
        suggested_title = f"fix: {task.name}"
        suggested_body = (
            "## Summary\n"
            f"- {task.config.issue_input}\n\n"
            "## Test\n"
            f"- {test_command}\n"
        )
        markdown = "\n".join(
            [
                f"# Agent 修复报告 - {task.name}",
                "",
                "## Issue 摘要",
                task.config.issue_input or "未提供 Issue 描述。",
                "",
                "## 根因分析",
                root_cause or "Agent 未输出明确根因；请结合 diff 和测试结果复核。",
                "",
                "## 修改文件列表",
                "\n".join(f"- {path}" for path in files) or "- 无",
                "",
                "## 关键修改说明",
                key_changes,
                "",
                "## 测试命令和测试结果",
                f"命令: `{test_command}`",
                "",
                "```text",
                test_output[:4000],
                "```",
                "",
                "## 剩余风险",
                "- 建议人工复核边界条件、异常输入和未覆盖路径。",
                "",
                "## 建议的 PR 标题",
                suggested_title,
                "",
                "## 建议的 PR 描述",
                suggested_body,
                "",
            ]
        )
        return FixReport(
            file_name=f"{task.id}-fix-report.md",
            markdown=markdown,
            suggested_pr_title=suggested_title,
            suggested_pr_description=suggested_body,
            created_at=_utcnow(),
        )

    def _build_metrics(
        self,
        task: EvaluationTaskRecord,
        result: EvaluationResult,
    ) -> list[MetricScore]:
        snapshot = result.current_state or RuntimeSnapshot(
            max_iterations=task.config.max_iterations)
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

    def _refresh_result(self, task: EvaluationTaskRecord) -> None:
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
        elif result.current_state and result.current_state.status == MAX_ITERATIONS_REACHED_STATUS:
            result.outcome = "running"
            result.summary = (
                f"已达到 max_iterations={result.current_state.max_iterations}，"
                "等待用户再次运行以延长对话继续。"
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
        task: EvaluationTaskRecord,
        state: dict[str, Any] | None = None,
    ) -> None:
        result = self._ensure_result(task)
        if state is None and task.id in self._runtime_handles:
            handle = self._runtime_handles[task.id]
            try:
                config = {"configurable": {"thread_id": handle.thread_id}}
                state = handle.orchestrator.graph.get_state(config).values or {}
            except Exception:
                state = None
        result.agent_trace = agent_trace_service.build_trace(task, result, state or {})

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
        self._refresh_agent_trace(task, state)

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
        self._refresh_agent_trace(task)
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
        current_state = handle.orchestrator.graph.get_state(config).values
        if current_state.get("status") == MAX_ITERATIONS_REACHED_STATUS:
            handle.orchestrator.reopen_after_terminal(handle.thread_id)
        task.status = "running"
        task.started_at = task.started_at or _utcnow()
        self._refresh_result(task)
        task_service.save_task_record(task)

        if mode == "step":
            async for event in handle.orchestrator.graph.astream(None, config=config, stream_mode="updates"):
                node_name = next(iter(event))
                self._append_timeline_entries(
                    task, node_name, event[node_name])
                state = handle.orchestrator.graph.get_state(config).values
                self._sync_state(task, state)
                task_service.save_task_record(task)
                break
        else:
            async for event in handle.orchestrator.graph.astream(None, config=config, stream_mode="updates"):
                node_name = next(iter(event))
                self._append_timeline_entries(
                    task, node_name, event[node_name])
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

    async def run(self, task_id: str, request: TaskRunRequest) -> EvaluationTaskRecord:
        task = task_service.get_task_record(task_id)
        if task is None:
            raise ValueError("Task not found")

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
            if any(not background_job.done() for task_key, background_job in self._background_jobs.items() if task_key != task_id):
                raise RuntimeError("当前已有其他任务在运行，gitIssueAssitant 运行时暂不支持并发执行。")

            task.status = "scheduled"
            self._refresh_result(task)
            task_service.save_task_record(task)
            self._background_jobs[task_id] = asyncio.create_task(
                self._execute(task_id, run_request))
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
        if task_id not in self._runtime_handles:
            raise RuntimeError("请先运行或初始化任务后再发送多轮对话消息。")
        content = payload.content.strip()
        if not content:
            raise ValueError("Message content cannot be empty")

        handle = self._runtime_handles[task_id]
        self._activate_runtime(handle)
        self._append_task_message(task, "user", content, replan=payload.replan)
        handle.orchestrator.inject_message(handle.thread_id, content, replan=payload.replan)

        config = {"configurable": {"thread_id": handle.thread_id}}
        current_state = handle.orchestrator.graph.get_state(config).values
        if current_state.get("status") in ("SUCCESS", "FAILED", MAX_ITERATIONS_REACHED_STATUS):
            handle.orchestrator.reopen_after_terminal(handle.thread_id)
            current_state = handle.orchestrator.graph.get_state(config).values
            self._append_task_message(
                task,
                "system",
                "已接收追加要求，任务已重新打开；请点击继续单步或自动执行。",
                replan=payload.replan,
            )
            task.status = "scheduled"
            task.finished_at = None

        self._sync_state(task, current_state)
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
            handle.manager.cleanup_current_session()

    def shutdown(self) -> None:
        for task_id in list(self._runtime_handles.keys()):
            self.clear_task_state(task_id)
        if self._sandbox_manager is not None:
            self._sandbox_manager.stop_all()
            self._sandbox_manager = None

    def terminate_after_sandbox_unavailable(self, task_id: str) -> EvaluationTaskRecord | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        self.clear_task_state(task_id)
        self._append_task_message(task, "system", "用户选择终止任务：Docker 沙箱不可用，未继续本地执行。")
        self._mark_failed(task, "用户选择终止任务：Docker 沙箱不可用，未继续本地执行。")
        return task

    def _repo_path_for_task(self, task: EvaluationTaskRecord) -> Path:
        repo_path = task.repo_path
        if not repo_path and task.result and task.result.current_state:
            repo_path = task.result.current_state.repo_path
        if not repo_path:
            raise ValueError("Task has no local repository path")

        resolved_repo_path = Path(repo_path).expanduser().resolve()
        if not resolved_repo_path.exists():
            raise ValueError(
                f"Repository path does not exist: {resolved_repo_path}")
        if not _is_git_repo(resolved_repo_path):
            raise ValueError(
                f"Path is not a Git repository: {resolved_repo_path}")
        return resolved_repo_path

    def get_git_diff(self, task_id: str) -> GitDiffResponse | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None

        repo_path = self._repo_path_for_task(task)
        status = _run_git_command(repo_path, ["status", "--short"], timeout=30)
        branch = _run_git_command(
            repo_path, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=10
        ).strip()
        diff_parts = [
            _run_git_command(
                repo_path, ["diff", "--no-ext-diff", "--binary"], timeout=60),
            _run_git_command(
                repo_path,
                ["diff", "--no-ext-diff", "--binary", "--cached"],
                timeout=60,
            ),
            _build_untracked_diff(repo_path),
        ]
        diff = "\n".join(part for part in diff_parts if part.strip())

        return GitDiffResponse(
            task_id=task.id,
            repo_path=str(repo_path),
            branch=branch,
            status=status,
            diff=diff,
            has_changes=bool(status.strip()),
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

        repo_path = self._repo_path_for_task(task)
        if not request.remote.strip():
            raise ValueError("Remote name cannot be empty")

        status = _run_git_command(repo_path, ["status", "--short"], timeout=30)
        if not status.strip():
            raise ValueError("No local changes to commit and push")

        commit_message = (
            request.commit_message.strip()
            if request.commit_message and request.commit_message.strip()
            else f"fix: {task.name}"
        )
        branch = request.branch.strip() if request.branch and request.branch.strip() else ""
        if not branch:
            branch = _run_git_command(
                repo_path,
                ["rev-parse", "--abbrev-ref", "HEAD"],
                timeout=10,
            ).strip()
        if not branch or branch == "HEAD":
            raise ValueError("Cannot push from a detached HEAD state")

        outputs = [
            _run_git_command(repo_path, ["add", "-A"], timeout=60),
            _run_git_command(
                repo_path, ["commit", "-m", commit_message], timeout=60),
        ]
        commit_hash = _run_git_command(
            repo_path, ["rev-parse", "--short", "HEAD"], timeout=10).strip()
        outputs.append(
            _run_git_command(
                repo_path,
                ["push", request.remote.strip(), branch],
                timeout=180,
            )
        )

        result = self._ensure_result(task)
        result.last_commit_hash = commit_hash
        task_service.save_task_record(task)
        return GitPushResponse(
            task_id=task.id,
            repo_path=str(repo_path),
            commit_hash=commit_hash,
            pushed=True,
            output="\n".join(output for output in outputs if output.strip()),
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

        repo_path = self._repo_path_for_task(task)
        remote = request.remote.strip() or "origin"
        status = _run_git_command(repo_path, ["status", "--short"], timeout=30)
        if not status.strip():
            raise ValueError("No local changes to commit for pull request")

        current_branch = _run_git_command(
            repo_path,
            ["rev-parse", "--abbrev-ref", "HEAD"],
            timeout=10,
        ).strip()
        if not current_branch or current_branch == "HEAD":
            raise ValueError(
                "Cannot create a pull request from a detached HEAD state")

        base_branch = request.base_branch.strip(
        ) if request.base_branch and request.base_branch.strip() else current_branch
        branch = request.branch.strip(
        ) if request.branch and request.branch.strip() else f"agent-fix-{task.id}"
        commit_message = request.commit_message.strip(
        ) if request.commit_message and request.commit_message.strip() else f"fix: {task.name}"
        report = self.get_fix_report(task_id)
        title = request.title.strip() if request.title and request.title.strip() else (
            report.suggested_pr_title if report else f"fix: {task.name}")
        body = request.body.strip() if request.body and request.body.strip() else (
            report.suggested_pr_description if report else "")

        remote_url = _run_git_command(
            repo_path, ["config", "--get", f"remote.{remote}.url"], timeout=10).strip()
        repo_info = _parse_github_remote(remote_url)
        if repo_info is None:
            raise ValueError(
                f"Remote {remote} is not a recognized GitHub remote: {remote_url}")
        owner, repo = repo_info

        outputs = [
            _run_git_command(
                repo_path, ["checkout", "-B", branch], timeout=30),
            _run_git_command(repo_path, ["add", "-A"], timeout=60),
            _run_git_command(
                repo_path, ["commit", "-m", commit_message], timeout=60),
        ]
        commit_hash = _run_git_command(
            repo_path, ["rev-parse", "--short", "HEAD"], timeout=10).strip()
        outputs.append(_run_git_command(
            repo_path, ["push", "-u", remote, branch], timeout=180))

        payload = {
            "title": title,
            "body": body,
            "head": branch,
            "base": base_branch,
        }
        pr_payload = _github_json_request(
            f"/repos/{owner}/{repo}/pulls", payload)
        result = self._ensure_result(task)
        result.last_commit_hash = commit_hash
        result.pull_request_url = pr_payload.get("html_url")
        task_service.save_task_record(task)
        return GitPullRequestResponse(
            task_id=task.id,
            repo_path=str(repo_path),
            branch=branch,
            base_branch=base_branch,
            commit_hash=commit_hash,
            pr_url=result.pull_request_url,
            output="\n".join(output for output in outputs if output.strip()),
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


evaluation_service = EvaluationService()
