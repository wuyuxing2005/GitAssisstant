import os
import re
import subprocess
import uuid
import json
from pathlib import Path
from typing import Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from langchain_core.messages import HumanMessage

from .orchestrator import AgentOrchestrator


class SessionManager:
    def __init__(self, orchestrator, workspace_root: str | Path | None = None):
        # 引用全局唯一的引擎
        self.orchestrator:AgentOrchestrator = orchestrator
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.repos_root = (self.workspace_root / "repos").resolve()
        self.repos_root.mkdir(parents=True, exist_ok=True)
        # 核心：维护 仓库路径 -> thread_id 的映射
        self.sessions: Dict[str, str] = {} 
        self.current_repo: Optional[str] = None

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
            text=True,
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

    def _resolve_repo_path(self, repo_ref: str, target_dir: str | None = None) -> Path:
        if self._is_git_url(repo_ref):
            repo_name = target_dir or self._sanitize_repo_name(repo_ref)
            destination = (self.repos_root / repo_name).resolve()
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                result = subprocess.run(
                    ["git", "clone", repo_ref, str(destination)],
                    capture_output=True,
                    text=True,
                    cwd=str(self.repos_root),
                )
                if result.returncode != 0:
                    error = result.stderr.strip() or result.stdout.strip() or "git clone 失败"
                    raise ValueError(error)
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

    def create_or_switch_session(self, repo_ref: str, target_dir: str | None = None):
        """创建或切换到一个仓库会话"""
        repo_path = str(self._resolve_repo_path(repo_ref, target_dir))

        if repo_path not in self.sessions:
            # 如果是新仓库，分配一个新的 thread_id
            safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", repo_path)
            self.sessions[repo_path] = f"thread_{safe_id}"
        
        # 切换当前指针
        self.current_repo = repo_path
        os.environ["GIT_ISSUE_ASSISTANT_REPO_ROOT"] = repo_path
        os.chdir(repo_path)
        return self.sessions[repo_path]

    def set_issue(self, issue_desc: str):
        """为当前仓库注入初始 Issue 并初始化状态"""
        if not self.current_repo:
            raise ValueError("请先使用 /repo 指定仓库")

        issue_desc = self.resolve_issue_description(issue_desc)
        repo_path = self.current_repo
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", repo_path)
        thread_id = f"thread_{safe_id}_{uuid.uuid4().hex[:8]}"
        self.sessions[repo_path] = thread_id
        config = {"configurable": {"thread_id": thread_id}}
        
        # 定义该仓库的初始状态 (AgentState)
        initial_state = {
            "repo_path": repo_path,
            "issue_description": issue_desc,
            "status": "INIT",
            "iteration_count": 0,
            "max_iterations": 15,
            "plan": [],
            "messages": [
                HumanMessage(
                    content=(
                        f"当前仓库路径：{self.current_repo}\n"
                        f"需要解决的问题：{issue_desc}\n"
                        "当前仓库已经在本地可用，除非明确缺失，否则不要再次克隆仓库。\n"
                        "请先理解仓库、定位相关代码、必要时运行测试或命令，"
                        "然后修改代码并验证结果。请尽量给出可验证的修复结论。"
                    )
                )
            ],
            "trajectory": [],
            "reflexion_notes": ""
        }
        
        # 将初始状态强行写入 LangGraph 的内存中
        self.orchestrator.graph.update_state(config, initial_state)

    def get_current_thread_id(self) -> str:
        """获取当前正在操作的 thread_id"""
        if not self.current_repo:
            raise ValueError("当前没有激活的仓库，请使用 /repo <path>")
        return self.sessions[self.current_repo]

    def get_current_state(self) -> dict:
        """获取当前仓库的实时状态数据"""
        thread_id = self.get_current_thread_id()
        config = {"configurable": {"thread_id": thread_id}}
        
        # 从 Orchestrator 的 MemorySaver 中读取对应的存档
        state_snapshot = self.orchestrator.graph.get_state(config)
        
        # 如果还没初始化过，返回空字典
        return state_snapshot.values if state_snapshot else {}
