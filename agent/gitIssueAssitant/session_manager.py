import os
import re
import subprocess
import uuid
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from langchain_core.messages import HumanMessage

from .orchestrator import AgentOrchestrator
from .persistence import AgentConversationStore, default_store_path


def _text_output_kwargs() -> dict[str, str | bool]:
    return {"text": True, "encoding": "utf-8", "errors": "replace"}


@dataclass
class Session:
    session_id: str
    thread_id: str
    repo_path: str
    issue_ref: Optional[str] = None
    issue_description: Optional[str] = None
    sandbox_error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SessionManager:
    def __init__(self, orchestrator, workspace_root: str | Path | None = None,
                 sandbox_manager=None, store: AgentConversationStore | None = None):
        self.orchestrator: AgentOrchestrator = orchestrator
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.repos_root = (self.workspace_root / "repos").resolve()
        self.repos_root.mkdir(parents=True, exist_ok=True)
        self.store = store or AgentConversationStore(default_store_path(self.workspace_root))
        # session_id -> Session
        self.sessions: Dict[str, Session] = self._load_persisted_sessions()
        self.current_session_id: Optional[str] = None
        self.sandbox_manager = sandbox_manager  # 沙箱管理器（迭代三第二组新增）
        self.orchestrator.state_persist_hook = self.persist_thread_state

    def _load_persisted_sessions(self) -> Dict[str, Session]:
        sessions: Dict[str, Session] = {}
        for row in self.store.list_sessions():
            sessions[row["session_id"]] = Session(
                session_id=row["session_id"],
                thread_id=row["thread_id"],
                repo_path=row["repo_path"],
                issue_ref=row.get("issue_ref"),
                issue_description=row.get("issue_description"),
                sandbox_error=row.get("sandbox_error"),
                created_at=row.get("created_at") or datetime.now().isoformat(),
            )
        return sessions

    def _persist_session(self, session: Session) -> None:
        self.store.save_session(session)

    def persist_current_state(self, last_node: str | None = None) -> None:
        session = self._current_session()
        if session is None:
            return
        self.persist_thread_state(session.thread_id, last_node)

    def persist_thread_state(self, thread_id: str, last_node: str | None = None) -> None:
        session = next(
            (item for item in self.sessions.values() if item.thread_id == thread_id),
            None,
        )
        if session is None:
            return
        config = {"configurable": {"thread_id": session.thread_id}}
        state_snapshot = self.orchestrator.graph.get_state(config)
        state = state_snapshot.values if state_snapshot else {}
        if state:
            self.store.save_state(
                session.session_id,
                session.thread_id,
                state,
                last_node=last_node,
            )
        self._persist_session(session)

    def _restore_graph_state(self, session: Session) -> None:
        record = self.store.load_state_record(session.thread_id)
        if not record:
            return
        state = record["state"]
        if not state:
            return
        config = {"configurable": {"thread_id": session.thread_id}}
        existing_snapshot = self.orchestrator.graph.get_state(config)
        if existing_snapshot and existing_snapshot.values:
            return
        last_node = record.get("last_node") or "__start__"
        try:
            self.orchestrator.graph.update_state(config, state, as_node=last_node)
        except Exception:
            self.orchestrator.graph.update_state(config, state)

    def _is_git_url(self, repo_ref: str) -> bool:
        return repo_ref.startswith(("http://", "https://", "git@")) or repo_ref.endswith(".git")

    def _sanitize_repo_name(self, repo_ref: str) -> str:
        name = repo_ref.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
        return name or "repo"

    def _parse_github_repo(self, remote_url: str) -> tuple[str, str] | None:
        patterns = [
            r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?/?$",
            r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/?",
        ]
        for pattern in patterns:
            match = re.search(pattern, remote_url)
            if match:
                return match.group("owner"), match.group("repo").removesuffix(".git")
        return None

    def _current_github_repo(self) -> tuple[str, str]:
        if not self.current_repo:
            raise ValueError("请先使用 /repo 指定仓库")

        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            **_text_output_kwargs(),
            cwd=self.current_repo,
        )
        remote_url = result.stdout.strip()
        if result.returncode != 0 or not remote_url:
            raise ValueError("当前仓库没有 remote.origin.url，无法根据 issue 编号定位 GitHub 仓库")

        repo_info = self._parse_github_repo(remote_url)
        if repo_info is None:
            raise ValueError(f"当前 remote 不是可识别的 GitHub 仓库: {remote_url}")
        return repo_info

    def _parse_issue_ref(self, issue_ref: str) -> tuple[str, str, int] | None:
        issue_ref = issue_ref.strip()
        url_match = re.search(
            r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)",
            issue_ref,
        )
        if url_match:
            return url_match.group("owner"), url_match.group("repo"), int(url_match.group("number"))

        number_match = re.fullmatch(r"#?(?P<number>\d+)", issue_ref)
        if number_match:
            owner, repo = self._current_github_repo()
            return owner, repo, int(number_match.group("number"))

        return None

    def _fetch_github_issue(self, owner: str, repo: str, issue_number: int) -> str:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "gitIssueAssitant",
        }
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = Request(api_url, headers=headers)
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"GitHub Issue 获取失败: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise ValueError(f"GitHub Issue 获取失败: {exc.reason}") from exc

        title = payload.get("title") or ""
        body = payload.get("body") or ""
        html_url = payload.get("html_url") or api_url
        return (
            f"GitHub Issue: {owner}/{repo}#{issue_number}\n"
            f"URL: {html_url}\n"
            f"Title: {title}\n\n"
            f"Body:\n{body}"
        ).strip()

    def resolve_issue_description(self, issue_ref: str) -> str:
        issue_info = self._parse_issue_ref(issue_ref)
        if issue_info is None:
            return issue_ref
        owner, repo, issue_number = issue_info
        return self._fetch_github_issue(owner, repo, issue_number)

    def _refresh_existing_clone(self, destination: Path) -> None:
        """复用已有 clone 时，把工作区强制重置到 origin 默认分支的最新状态。

        防止上次会话残留的本地 commit / reset / 未跟踪文件影响新会话的 verify 逻辑
        （例如出现工作区与 HEAD 不一致、git diff 为空但 issue 实际未修等情况）。
        """

        def run(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(
                cmd, capture_output=True, **_text_output_kwargs(), cwd=str(destination)
            )

        fetch = run(["git", "fetch", "--prune", "origin"])
        if fetch.returncode != 0:
            print(
                f"⚠️ git fetch 失败，跳过重置，沿用本地状态: "
                f"{(fetch.stderr or fetch.stdout).strip()}"
            )
            return

        default_branch = ""
        head_ref = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
        if head_ref.returncode == 0:
            default_branch = head_ref.stdout.strip().rsplit("/", 1)[-1]
        else:
            run(["git", "remote", "set-head", "origin", "--auto"])
            head_ref = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
            if head_ref.returncode == 0:
                default_branch = head_ref.stdout.strip().rsplit("/", 1)[-1]

        if not default_branch:
            for candidate in ("main", "master"):
                check = run(["git", "rev-parse", "--verify", f"origin/{candidate}"])
                if check.returncode == 0:
                    default_branch = candidate
                    break

        if not default_branch:
            print("⚠️ 无法判定 origin 默认分支，跳过重置。")
            return

        run(["git", "checkout", default_branch])
        reset = run(["git", "reset", "--hard", f"origin/{default_branch}"])
        run(["git", "clean", "-fd"])
        if reset.returncode == 0:
            print(
                f"🔄 复用已有 clone，已重置到 origin/{default_branch} 并清理工作区。"
            )
        else:
            print(f"⚠️ 重置失败: {(reset.stderr or reset.stdout).strip()}")

    def _resolve_repo_path(self, repo_ref: str, target_dir: str | None = None) -> Path:
        if self._is_git_url(repo_ref):
            repo_name = target_dir or self._sanitize_repo_name(repo_ref)
            destination = (self.repos_root / repo_name).resolve()
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                result = subprocess.run(
                    ["git", "clone", repo_ref, str(destination)],
                    capture_output=True,
                    **_text_output_kwargs(),
                    cwd=str(self.repos_root),
                )
                if result.returncode != 0:
                    error = result.stderr.strip() or result.stdout.strip() or "git clone 失败"
                    raise ValueError(error)
            else:
                self._refresh_existing_clone(destination)
            return destination

        candidate = Path(repo_ref)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            repos_candidate = (self.repos_root / candidate).resolve()
            workspace_candidate = (self.workspace_root / candidate).resolve()
            resolved = repos_candidate if repos_candidate.exists() else workspace_candidate
        if not resolved.exists():
            raise ValueError(f"仓库不存在: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"仓库路径不是目录: {resolved}")
        return resolved

    @property
    def current_repo(self) -> Optional[str]:
        session = self._current_session()
        return session.repo_path if session else None

    def _current_session(self) -> Optional[Session]:
        if not self.current_session_id:
            return None
        return self.sessions.get(self.current_session_id)

    def _find_sessions_by(self, repo_path: str, issue_ref: Optional[str] = None) -> list[Session]:
        """查找具有相同 repo + issue 组合的已有会话"""
        results = []
        for s in self.sessions.values():
            if s.repo_path == repo_path:
                if issue_ref is None or s.issue_ref == issue_ref:
                    results.append(s)
        return results

    def create_session(self, repo_ref: str, issue_ref: Optional[str] = None,
                       target_dir: str | None = None, force: bool = False) -> tuple[Session, Optional[list[Session]]]:
        """创建新会话。返回 (新会话, 重复会话列表或None)。

        如果存在相同 repo+issue 的会话且 force=False，返回重复列表供调用方提示用户。
        force=True 时跳过检查直接创建。
        """
        repo_path = str(self._resolve_repo_path(repo_ref, target_dir))

        duplicates: Optional[list[Session]] = None
        if issue_ref and not force:
            existing = self._find_sessions_by(repo_path, issue_ref)
            if existing:
                duplicates = existing

        session_id = uuid.uuid4().hex[:12]
        thread_id = f"thread_{session_id}"
        session = Session(
            session_id=session_id,
            thread_id=thread_id,
            repo_path=repo_path,
            issue_ref=issue_ref,
        )
        self.sessions[session_id] = session
        self._switch_to(session)
        self._persist_session(session)
        return session, duplicates

    def switch_session(self, session_id: str) -> Session:
        """切换到已有会话"""
        if session_id not in self.sessions:
            raise ValueError(f"会话不存在: {session_id}")
        session = self.sessions[session_id]
        self._switch_to(session)
        return session

    def list_sessions(self, repo_path: Optional[str] = None) -> list[Session]:
        """列出所有会话，可按仓库过滤"""
        if repo_path:
            return [s for s in self.sessions.values() if s.repo_path == repo_path]
        return list(self.sessions.values())

    def get_session(self, session_id: str) -> Session:
        """获取指定会话。"""
        if session_id not in self.sessions:
            raise ValueError(f"会话不存在: {session_id}")
        return self.sessions[session_id]

    def get_session_state(self, session_id: str) -> dict:
        """获取指定会话的实时状态数据，不切换当前会话。"""
        session = self.get_session(session_id)
        self._restore_graph_state(session)
        config = {"configurable": {"thread_id": session.thread_id}}
        state_snapshot = self.orchestrator.graph.get_state(config)
        return state_snapshot.values if state_snapshot else {}

    def _switch_to(self, session: Session):
        self.current_session_id = session.session_id
        os.environ["GIT_ISSUE_ASSISTANT_REPO_ROOT"] = session.repo_path
        if Path(session.repo_path).exists():
            os.chdir(session.repo_path)
        else:
            print(f"[会话] 仓库路径不存在，暂时停留在工作区目录: {session.repo_path}")
            os.chdir(self.workspace_root)
        self._restore_graph_state(session)

    def set_issue(self, issue_desc: str):
        """为当前会话注入初始 Issue 并初始化状态。

        迭代三第二组新增：如果 sandbox_manager 可用，在此处启动 Docker 沙箱，
        并将 repo_path 指向沙箱内的宿主工作副本。
        """
        session = self._current_session()
        if not session:
            raise ValueError("当前没有激活的会话，请先创建会话")

        resolved_desc = self.resolve_issue_description(issue_desc)
        session.issue_ref = issue_desc
        session.issue_description = resolved_desc
        session.sandbox_error = None
        self._persist_session(session)

        # ---- 沙箱启动（迭代三第二组新增）----
        sandbox_id = ""
        if self.sandbox_manager is not None:
            # 保留原始仓库路径（沙箱外），供 cleanup 时参考
            original_repo_path = session.repo_path
            try:
                sandbox = self.sandbox_manager.get_or_create(
                    session.thread_id, original_repo_path
                )
                # 将工作目录切换到沙箱的宿主副本
                session.repo_path = str(sandbox.host_work_dir)
                os.environ["GIT_ISSUE_ASSISTANT_REPO_ROOT"] = session.repo_path
                os.chdir(session.repo_path)
                sandbox_id = session.thread_id
                print(
                    f"[沙箱] 沙箱容器已就绪 (sandbox_id={sandbox_id})\n"
                    f"       容器名: {sandbox.container_name}\n"
                    f"       宿主工作目录: {sandbox.host_work_dir}\n"
                    f"       容器工作目录: /workspace/repo"
                )
            except Exception as exc:
                session.sandbox_error = str(exc)
                print(f"[沙箱] 沙箱启动失败，回退到本地执行模式: {exc}")
                sandbox_id = ""
            finally:
                self._persist_session(session)

        config = {"configurable": {"thread_id": session.thread_id}}

        initial_state = {
            "repo_path": session.repo_path,
            "issue_description": resolved_desc,
            "status": "INIT",
            "iteration_count": 0,
            "goals": [],
            "current_goal_index": 0,
            "plan_version": 0,
            "replan_trigger": "",
            "reflexion_notes": "",
            "sandbox_id": sandbox_id,  # 迭代三第二组新增
            "tool_call_events": [],    # 迭代三第二组新增
            "messages": [
                HumanMessage(
                    content=(
                        f"当前仓库路径：{session.repo_path}\n"
                        f"需要解决的问题：{resolved_desc}\n"
                        "当前仓库已经在本地可用，除非明确缺失，否则不要再次克隆仓库。\n"
                        "请先理解仓库、定位相关代码、必要时运行测试或命令，"
                        "然后修改代码并验证结果。请尽量给出可验证的修复结论。"
                    )
                )
            ],
            "trajectory": [],
        }

        # 检测是否已有历史状态（同一会话中连续解决多个 Issue）
        # 若有历史 checkpoint（上一个 Issue 已结束），需将图位置重置到入口节点，
        # 否则 astream(None) 会从 END 出发、立即返回空结果。
        state_snapshot = self.orchestrator.graph.get_state(config)
        if state_snapshot and state_snapshot.values and state_snapshot.values.get("status") not in ("", "INIT"):
            self.orchestrator.graph.update_state(config, initial_state, as_node="__start__")
            print("[会话] 检测到已有历史状态，已用 as_node='__start__' 重置 graph 位置。")
        else:
            self.orchestrator.graph.update_state(config, initial_state)
        self.persist_current_state(last_node="__start__")

    def get_current_thread_id(self) -> str:
        """获取当前会话的 thread_id"""
        session = self._current_session()
        if not session:
            raise ValueError("当前没有激活的会话")
        return session.thread_id

    def get_current_state(self) -> dict:
        """获取当前会话的实时状态数据"""
        thread_id = self.get_current_thread_id()
        config = {"configurable": {"thread_id": thread_id}}
        state_snapshot = self.orchestrator.graph.get_state(config)
        return state_snapshot.values if state_snapshot else {}

    def cleanup_current_session(self):
        """清理当前会话的沙箱资源（停止容器、清理工作目录）。

        在会话结束或切换时调用。"""
        if self.sandbox_manager is None:
            return
        session = self._current_session()
        if session is None:
            return
        # 清理沙箱
        self.sandbox_manager.stop(session.thread_id)
        self.sandbox_manager.cleanup(session.thread_id)
        print(f"[沙箱] 已清理会话 {session.session_id} 的沙箱资源。")

    def cleanup_all_sessions(self):
        """程序退出时清理所有会话的沙箱资源。"""
        if self.sandbox_manager is None:
            return
        for session in list(self.sessions.values()):
            self.sandbox_manager.stop(session.thread_id)
        print("[沙箱] 已清理所有沙箱资源。")
