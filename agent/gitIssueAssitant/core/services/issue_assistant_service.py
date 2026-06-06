from __future__ import annotations

import os
from pathlib import Path
from typing import Any, AsyncIterator

from dotenv import load_dotenv

from ..agent import Agent, AgentOrchestrator, LLM_factory
from ..agent.skills import SkillRegistry
from ..agent.tools.registry import ToolRegistry, setup_default_registry
from ..agent.tools.sandbox_manager import SandboxManager
from ..agent.tools.tools import (
    AGENT_TOOLS,
    AGENT_TOOLS_ALL,
    _git_add_impl,
    _git_commit_impl,
    _git_push_impl,
    clear_active_sandbox,
)
from ..domain.git_workflow import GitDiffResult, GitPullRequestResult, GitPushResult
from ..domain.session import Session
from ..utils.git import (
    current_git_branch,
    git_status_short,
    is_git_repo,
    run_git_command,
    working_tree_diff_for_commit,
)
from ..utils.github_pr import create_github_pr
from ..utils.reports import (
    build_fix_report_markdown,
    build_fix_report_markdown_from_context,
    write_fix_report,
)
from ..utils.commit_plan import get_commit_plan_from_agent
from .session_service import SessionService
from .task_service import task_service


AGENT_DISABLED_GIT_TOOL_NAMES = {"git_add", "git_commit", "git_push"}


class IssueAssistantService:
    """Facade used by CLI and REST adapters to access assistant workflows."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        orchestrator: AgentOrchestrator | None,
        session_service: SessionService | None,
        sandbox_manager: SandboxManager | None = None,
        loaded_skills: dict[str, Any] | None = None,
        registry: ToolRegistry | None = None,
        task_runtime: Any | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.orchestrator = orchestrator
        self.session_service = session_service
        self.sandbox_manager = sandbox_manager
        self.loaded_skills = loaded_skills or {}
        self.registry = registry
        self._task_runtime = task_runtime

    @classmethod
    def create(
        cls,
        *,
        workspace_root: str | Path,
        tools: list | None = None,
        skill_registry: SkillRegistry | None = None,
        registry: ToolRegistry | None = None,
        sandbox_manager: SandboxManager | None = None,
        model_name: str | None = None,
    ) -> "IssueAssistantService":
        workspace = Path(workspace_root).resolve()
        os.environ["GIT_ISSUE_ASSISTANT_HOME"] = str(workspace)
        model = LLM_factory(model_name)
        agent = Agent(model)
        if skill_registry is None:
            skills = SkillRegistry()
            loaded_skills = skills.load()
        else:
            skills = skill_registry
            loaded_skills = dict(skills._skills) if skills._loaded else skills.load()
        orchestrator = AgentOrchestrator(
            agent,
            tools=tools or AGENT_TOOLS,
            skill_registry=skills,
            registry=registry,
            sandbox_manager=sandbox_manager,
        )
        session_service = SessionService(
            orchestrator,
            workspace_root=workspace,
            sandbox_manager=sandbox_manager,
        )
        return cls(
            workspace_root=workspace,
            orchestrator=orchestrator,
            session_service=session_service,
            sandbox_manager=sandbox_manager,
            loaded_skills=loaded_skills,
            registry=registry,
        )

    @classmethod
    def create_for_cli(cls, workspace_root: str | Path) -> "IssueAssistantService":
        workspace = Path(workspace_root).resolve()
        load_dotenv(workspace / ".env")
        os.environ["GIT_ISSUE_ASSISTANT_HOME"] = str(workspace)
        registry = setup_default_registry(AGENT_TOOLS_ALL)
        registry.hard_disable("git_push")
        enable_sandbox = os.getenv("GIT_ISSUE_ASSISTANT_DISABLE_SANDBOX", "").lower() not in ("1", "true", "yes")
        sandbox_manager = SandboxManager(workspace_root=workspace) if enable_sandbox else None
        return cls.create(
            workspace_root=workspace,
            tools=AGENT_TOOLS,
            registry=registry,
            sandbox_manager=sandbox_manager,
        )

    @classmethod
    def create_for_adapter(cls, workspace_root: str | Path) -> "IssueAssistantService":
        workspace = Path(workspace_root).resolve()
        os.environ["GIT_ISSUE_ASSISTANT_HOME"] = str(workspace)
        return cls(
            workspace_root=workspace,
            orchestrator=None,
            session_service=None,
        )

    @classmethod
    def create_for_rest_runtime(
        cls,
        *,
        workspace_root: str | Path,
        enabled_skill_names: set[str],
        sandbox_manager: SandboxManager | None,
        model_name: str | None = None,
    ) -> "IssueAssistantService":
        workspace = Path(workspace_root).resolve()
        web_safe_tools = [
            tool
            for tool in AGENT_TOOLS
            if getattr(tool, "name", "") not in AGENT_DISABLED_GIT_TOOL_NAMES
        ]
        skill_registry = SkillRegistry(workspace / "gitIssueAssitant" / "core" / "agent" / "skills")
        skill_registry.load()
        skill_registry._skills = {
            name: skill
            for name, skill in skill_registry._skills.items()
            if name in enabled_skill_names
        }
        return cls.create(
            workspace_root=workspace,
            tools=web_safe_tools,
            skill_registry=skill_registry,
            sandbox_manager=sandbox_manager,
            model_name=model_name,
        )

    @property
    def current_repo(self) -> str | None:
        return self._session_service.current_repo

    @property
    def current_session_id(self) -> str | None:
        return self._session_service.current_session_id

    @property
    def _orchestrator(self) -> AgentOrchestrator:
        if self.orchestrator is None:
            raise RuntimeError("当前 IssueAssistantService 未初始化交互式 agent runtime。")
        return self.orchestrator

    @property
    def _session_service(self) -> SessionService:
        if self.session_service is None:
            raise RuntimeError("当前 IssueAssistantService 未初始化 session runtime。")
        return self.session_service

    def _tasks(self):
        if self._task_runtime is None:
            from .util.task_runtime import _IssueAssistantTaskRuntime

            self._task_runtime = _IssueAssistantTaskRuntime(workspace_root=self.workspace_root)
        return self._task_runtime

    def current_session(self) -> Session | None:
        return self._session_service.current_session()

    def create_session(self, repo_ref: str, *, target_dir: str | None = None, force: bool = False):
        return self._session_service.create_session(repo_ref, target_dir=target_dir, force=force)

    def switch_session(self, session_id: str) -> Session:
        return self._session_service.switch_session(session_id)

    def switch_session_by_thread_id(self, thread_id: str) -> Session:
        return self._session_service.switch_session_by_thread_id(thread_id)

    def list_sessions(self) -> list[Session]:
        return self._session_service.list_sessions()

    def get_session(self, session_id: str) -> Session:
        return self._session_service.get_session(session_id)

    def get_session_state(self, session_id: str) -> dict:
        return self._session_service.get_session_state(session_id)

    def set_issue(self, issue_desc: str) -> None:
        self._session_service.set_issue(issue_desc)

    def get_current_thread_id(self) -> str:
        return self._session_service.get_current_thread_id()

    def get_current_state(self) -> dict:
        return self._session_service.get_current_state()

    async def run_step(self, thread_id: str) -> None:
        await self._orchestrator.run_step(thread_id)

    def run_auto_interactive(self, thread_id: str, *, verbose: bool = False) -> AsyncIterator[Any]:
        return self._orchestrator.run_auto_interactive(thread_id, verbose=verbose)

    def inject_message(self, thread_id: str, content: str, *, replan: bool = False) -> None:
        self._orchestrator.inject_message(thread_id, content, replan=replan)

    def reopen_after_terminal(self, thread_id: str) -> None:
        self._orchestrator.reopen_after_terminal(thread_id)

    async def raw_chat(self, text: str):
        return await self._orchestrator.raw_chat(text)

    def activate_runtime(self, thread_id: str) -> None:
        os.environ["GIT_ISSUE_ASSISTANT_HOME"] = str(self.workspace_root)
        if self.current_repo:
            os.environ["GIT_ISSUE_ASSISTANT_REPO_ROOT"] = self.current_repo
            os.chdir(self.current_repo)
        clear_active_sandbox()
        state = self.graph_state(thread_id)
        sandbox_id = str(state.get("sandbox_id") or "")
        sandbox = self.sandbox_manager.get(sandbox_id) if sandbox_id and self.sandbox_manager else None
        if sandbox is not None and getattr(sandbox, "_started", False):
            from ..agent.tools.tools import set_active_sandbox

            set_active_sandbox(sandbox)
            self._orchestrator._sandbox_activated = True
        else:
            self._orchestrator._sandbox_activated = False

    def graph_state(self, thread_id: str) -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = self._orchestrator.graph.get_state(config)
        return snapshot.values if snapshot else {}

    def update_graph_state(self, thread_id: str, state: dict, *, as_node: str | None = None) -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        if as_node:
            self._orchestrator.graph.update_state(config, state, as_node=as_node)
        else:
            self._orchestrator.graph.update_state(config, state)
        return self.graph_state(thread_id)

    def stream_graph_updates(self, thread_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        return self._orchestrator.graph.astream(None, config=config, stream_mode="updates")

    def persist_state(self, thread_id: str, node_name: str | None = None) -> None:
        self._orchestrator.persist_state(thread_id, node_name)

    def cleanup_current_session(self) -> None:
        self._session_service.cleanup_current_session()

    def shutdown(self) -> None:
        if self._task_runtime is not None:
            self._task_runtime.shutdown()
        clear_active_sandbox()
        if self.sandbox_manager:
            self.sandbox_manager.stop_all()

    def clear_runtime_sandbox(self) -> None:
        clear_active_sandbox()
        self._orchestrator._sandbox_activated = False

    def effective_issue_description(self, state: dict) -> str:
        return self._orchestrator.effective_issue_description(state)

    def working_tree_diff_for_commit(self, repo_path: str) -> str:
        return working_tree_diff_for_commit(repo_path)

    async def build_commit_plan(self, state: dict, diff: str) -> dict | None:
        return await get_commit_plan_from_agent(
            self._orchestrator.agent.llm,
            self.effective_issue_description(state),
            diff,
        )

    def build_fix_report(self, state: dict, diff: str, commit_plan: dict | None):
        return build_fix_report_markdown(
            state,
            self.effective_issue_description(state),
            diff,
            commit_plan,
        )

    def write_fix_report(self, markdown: str, session_id: str | None):
        return write_fix_report(markdown, session_id)

    def list_tasks(self):
        return task_service.list_tasks()

    def create_task(self, payload):
        return task_service.create_task(payload)

    def get_task(self, task_id: str):
        return task_service.get_task(task_id)

    def update_task(self, task_id: str, payload):
        task = task_service.update_task(task_id, payload)
        if task is not None and getattr(payload, "config", None) is not None:
            self.clear_task_state(task_id)
        return task

    def delete_task(self, task_id: str) -> bool:
        self.clear_task_state(task_id)
        return task_service.delete_task(task_id)

    async def run_task(self, task_id: str, request):
        return await self._tasks().run(task_id, request)

    def clear_task_state(self, task_id: str) -> None:
        self._tasks().clear_task_state(task_id)

    def recover_interrupted_tasks(self) -> int:
        return self._tasks().recover_interrupted_tasks()

    def terminate_after_sandbox_unavailable(self, task_id: str):
        return self._tasks().terminate_after_sandbox_unavailable(task_id)

    def get_task_result(self, task_id: str):
        return self._tasks().get_result(task_id)

    def get_task_trace(self, task_id: str):
        return self._tasks().get_trace(task_id)

    def get_task_messages(self, task_id: str):
        return self._tasks().get_messages(task_id)

    def submit_task_message(self, task_id: str, payload):
        return self._tasks().submit_message(task_id, payload)

    def get_task_git_diff(self, task_id: str):
        return self._tasks().get_git_diff(task_id)

    def get_task_fix_report(self, task_id: str):
        return self._tasks().get_fix_report(task_id)

    def push_task_changes(self, task_id: str, request):
        return self._tasks().push_changes(task_id, request)

    def create_task_pull_request(self, task_id: str, request):
        return self._tasks().create_pull_request(task_id, request)

    def compare_tasks(self, task_ids: list[str]):
        return self._tasks().compare(task_ids)

    def export_tasks_report_markdown(self, task_ids: list[str]) -> str:
        return self._tasks().export_report_markdown(task_ids)

    def export_tasks_report_csv(self, task_ids: list[str]) -> str:
        return self._tasks().export_report_csv(task_ids)

    @staticmethod
    def resolve_git_repo(repo_path: str | Path) -> Path:
        resolved_repo_path = Path(repo_path).expanduser().resolve()
        if not resolved_repo_path.exists():
            raise ValueError(f"Repository path does not exist: {resolved_repo_path}")
        if not is_git_repo(resolved_repo_path):
            raise ValueError(f"Path is not a Git repository: {resolved_repo_path}")
        return resolved_repo_path

    @classmethod
    def get_repository_diff(cls, repo_path: str | Path) -> GitDiffResult:
        repo = cls.resolve_git_repo(repo_path)
        status = git_status_short(repo)
        branch = current_git_branch(repo)
        diff = working_tree_diff_for_commit(repo)
        return GitDiffResult(
            repo_path=str(repo),
            branch=branch,
            status=status,
            diff=diff,
            has_changes=bool(status.strip()),
        )

    @staticmethod
    def build_fix_report_from_context(
        *,
        report_title: str,
        issue_description: str,
        diff: str,
        root_cause: str = "",
        test_command: str = "未检测到测试命令",
        test_output: str = "未检测到测试输出",
        commit_plan: dict | None = None,
    ) -> tuple[str, str, str]:
        return build_fix_report_markdown_from_context(
            report_title=report_title,
            issue_description=issue_description,
            diff=diff,
            root_cause=root_cause,
            test_command=test_command,
            test_output=test_output,
            commit_plan=commit_plan,
        )

    @classmethod
    def push_repository_changes(
        cls,
        *,
        repo_path: str | Path,
        commit_message: str,
        remote: str = "origin",
        branch: str | None = None,
        files: list[str] | None = None,
    ) -> GitPushResult:
        repo = cls.resolve_git_repo(repo_path)
        remote_name = remote.strip()
        if not remote_name:
            raise ValueError("Remote name cannot be empty")

        status = git_status_short(repo)
        if not status.strip():
            raise ValueError("No local changes to commit and push")

        target_branch = branch.strip() if branch and branch.strip() else current_git_branch(repo)
        if not target_branch or target_branch == "HEAD":
            raise ValueError("Cannot push from a detached HEAD state")

        add_args = ["add", *(files or ["-A"])]
        outputs = [
            run_git_command(repo, add_args, timeout=60),
            run_git_command(repo, ["commit", "-m", commit_message], timeout=60),
        ]
        commit_hash = run_git_command(repo, ["rev-parse", "--short", "HEAD"], timeout=10).strip()
        outputs.append(
            run_git_command(repo, ["push", remote_name, target_branch], timeout=180)
        )
        return GitPushResult(
            repo_path=str(repo),
            commit_hash=commit_hash,
            pushed=True,
            output="\n".join(output for output in outputs if output.strip()),
        )

    @classmethod
    def create_repository_pull_request(
        cls,
        *,
        repo_path: str | Path,
        commit_message: str,
        title: str,
        body: str,
        branch: str,
        base_branch: str | None = None,
        remote: str = "origin",
        files: list[str] | None = None,
    ) -> GitPullRequestResult:
        repo = cls.resolve_git_repo(repo_path)
        remote_name = remote.strip() or "origin"
        status = git_status_short(repo)
        if not status.strip():
            raise ValueError("No local changes to commit for pull request")

        current_branch = current_git_branch(repo)
        if not current_branch or current_branch == "HEAD":
            raise ValueError("Cannot create a pull request from a detached HEAD state")

        target_base = base_branch.strip() if base_branch and base_branch.strip() else current_branch
        target_branch = branch.strip()
        if not target_branch:
            raise ValueError("Pull request branch cannot be empty")

        outputs = [
            run_git_command(repo, ["checkout", "-B", target_branch], timeout=30),
            run_git_command(repo, ["add", *(files or ["-A"])], timeout=60),
            run_git_command(repo, ["commit", "-m", commit_message], timeout=60),
        ]
        commit_hash = run_git_command(repo, ["rev-parse", "--short", "HEAD"], timeout=10).strip()
        outputs.append(
            run_git_command(repo, ["push", "-u", remote_name, target_branch], timeout=180)
        )
        pr_url = create_github_pr(
            str(repo),
            target_branch,
            target_base,
            title,
            body,
            remote=remote_name,
        )
        return GitPullRequestResult(
            repo_path=str(repo),
            branch=target_branch,
            base_branch=target_base,
            commit_hash=commit_hash,
            pr_url=pr_url,
            output="\n".join(output for output in outputs if output.strip()),
        )

    def add_commit_push(self, files: list[str], message: str) -> tuple[str, str, str | None]:
        add_result = _git_add_impl(files)
        commit_result = _git_commit_impl(message)
        push_result = None
        if "nothing to commit" not in commit_result.lower():
            push_result = _git_push_impl()
        return add_result, commit_result, push_result

    def create_pull_request_from_plan(
        self,
        *,
        repo_path: str,
        files: list[str],
        commit_message: str,
        title: str,
        body: str,
        branch_name: str,
    ) -> tuple[str, str, str, str]:
        result = self.create_repository_pull_request(
            repo_path=repo_path,
            files=files,
            commit_message=commit_message,
            title=title,
            body=body,
            branch=branch_name,
        )
        return result.base_branch, result.output, result.output, result.pr_url or ""


#CLI启动即拥有一个完整 assistant，服务当前交互式终端。
# 通过命令切换Session

#WEB使用facade 模式
# 根据选择的任务，接到请求更改Session
issue_assistant_service = IssueAssistantService.create_for_adapter(
    Path(__file__).resolve().parents[3]
)
