from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models.task import EvaluationTaskRecord
from app.schemas.task import (
    GitHubIssueComment,
    GitHubIssueCommentRequest,
    GitHubIssueCommentResponse,
    GitHubIssueInfo,
    GitHubIssueLabelsRequest,
    GitHubIssueLabelsResponse,
    GitHubIssueStateRequest,
    GitHubIssueStateResponse,
    GitHubIssueSummary,
)
from app.services.settings_service import settings_service
from app.services.task_service import task_service


class GitHubIssueError(RuntimeError):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


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


def _parse_issue_url(issue_input: str) -> tuple[str, str, int] | None:
    match = re.search(
        r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)",
        issue_input.strip(),
    )
    if not match:
        return None
    return (
        match.group("owner"),
        match.group("repo").removesuffix(".git"),
        int(match.group("number")),
    )


def _parse_issue_number(issue_input: str) -> int | None:
    stripped = issue_input.strip()
    match = re.fullmatch(r"#?(?P<number>\d+)", stripped)
    return int(match.group("number")) if match else None


def _parse_repo_source(repo_source: str) -> tuple[str, str] | None:
    remote_info = _parse_github_remote(repo_source)
    if remote_info is not None:
        return remote_info
    match = re.fullmatch(
        r"(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?",
        repo_source.strip().strip("/"),
    )
    if not match:
        return None
    return match.group("owner"), match.group("repo").removesuffix(".git")


def _run_git(repo_path: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError((completed.stderr or completed.stdout).strip() or "Git command failed")
    return completed.stdout.strip()


def _token() -> str:
    return settings_service.get_settings().github_token.strip()


def _github_error_message(exc: HTTPError, operation: str) -> str:
    detail = exc.read().decode("utf-8", errors="replace")
    if exc.code == 401:
        return f"{operation} failed: GitHub token is invalid or expired. HTTP 401 {detail}"
    if exc.code == 403:
        remaining = exc.headers.get("X-RateLimit-Remaining", "")
        if remaining == "0":
            return f"{operation} failed: GitHub API rate limit exceeded. HTTP 403 {detail}"
        return f"{operation} failed: GitHub token lacks permission or the resource is forbidden. HTTP 403 {detail}"
    if exc.code == 404:
        return f"{operation} failed: GitHub issue/repository not found or token has no access. HTTP 404 {detail}"
    return f"{operation} failed: HTTP {exc.code} {detail}"


def _github_json_request(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    require_token: bool = False,
    operation: str = "GitHub issue request",
) -> Any:
    token = _token()
    if require_token and not token:
        raise GitHubIssueError("GITHUB_TOKEN is required for GitHub Issue write operations", 401)

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gitIssueAssitant",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"

    request = Request(
        f"https://api.github.com{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        raise GitHubIssueError(_github_error_message(exc, operation), exc.code) from exc
    except URLError as exc:
        raise GitHubIssueError(f"{operation} failed: {exc.reason}") from exc


class GitHubIssueService:
    def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 30,
    ) -> list[GitHubIssueSummary]:
        payload = _github_json_request(
            f"/repos/{owner}/{repo}/issues?state={state}&per_page={per_page}&sort=updated&direction=desc",
            operation="GitHub issues list",
        )
        if not isinstance(payload, list):
            return []
        results: list[GitHubIssueSummary] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            if item.get("pull_request"):
                continue
            labels = [
                str(label.get("name"))
                for label in item.get("labels", [])
                if isinstance(label, dict) and label.get("name")
            ]
            results.append(
                GitHubIssueSummary(
                    number=int(item.get("number", 0)),
                    title=str(item.get("title", "")),
                    body=str(item.get("body", "")),
                    state=str(item.get("state", "")),
                    labels=labels,
                    html_url=str(item.get("html_url", "")),
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at"),
                )
            )
        return results

    def _repo_path_for_task(self, task: EvaluationTaskRecord) -> Path | None:
        repo_path = task.repo_path
        if not repo_path and task.result and task.result.current_state:
            repo_path = task.result.current_state.repo_path
        if not repo_path:
            return None
        return Path(repo_path).expanduser().resolve()

    def _resolve_issue(self, task: EvaluationTaskRecord) -> tuple[str, str, int]:
        issue_from_url = _parse_issue_url(task.config.issue_input)
        if issue_from_url is not None:
            return issue_from_url

        issue_number = _parse_issue_number(task.config.issue_input)
        if issue_number is None:
            raise ValueError("Task is not associated with a GitHub Issue")

        repo_info = _parse_repo_source(task.config.repo_source)
        if repo_info is not None:
            owner, repo = repo_info
            return owner, repo, issue_number

        repo_path = self._repo_path_for_task(task)
        if repo_path is None:
            raise ValueError("Task has no local repository path for resolving issue number")
        remote_url = _run_git(repo_path, ["config", "--get", "remote.origin.url"])
        repo_info = _parse_github_remote(remote_url)
        if repo_info is None:
            raise ValueError(f"origin is not a recognized GitHub remote: {remote_url}")
        owner, repo = repo_info
        return owner, repo, issue_number

    def _build_default_comment(self, task: EvaluationTaskRecord) -> str:
        lines = [
            "## GitIssueAssitant 修复结果",
            "",
            f"- 任务：{task.name}",
            f"- 状态：{task.status}",
        ]
        if task.result:
            publish_lines: list[str] = []
            if task.result.pull_request_url:
                publish_lines.append(f"- PR：{task.result.pull_request_url}")
            if task.result.last_commit_hash:
                publish_lines.append(f"- Commit：{task.result.last_commit_hash}")
            if publish_lines:
                lines.extend(["", "### 发布信息", *publish_lines])
            if task.result.summary:
                lines.extend(["", "### 摘要", task.result.summary])
            if task.result.logs_preview:
                lines.extend(["", "### 测试/验证输出", "```text"])
                lines.extend(task.result.logs_preview[-20:])
                lines.append("```")
            if task.result.fix_report and task.result.fix_report.markdown:
                lines.extend(["", "### 修复报告", task.result.fix_report.markdown])
        return "\n".join(lines).strip()

    def get_issue(self, task_id: str, *, include_comments: bool = False) -> GitHubIssueInfo | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        owner, repo, number = self._resolve_issue(task)
        issue_payload = _github_json_request(
            f"/repos/{owner}/{repo}/issues/{number}",
            operation="GitHub issue fetch",
        )
        labels = [
            str(label.get("name"))
            for label in issue_payload.get("labels", [])
            if isinstance(label, dict) and label.get("name")
        ]
        comments: list[GitHubIssueComment] = []
        if include_comments:
            comments_payload = _github_json_request(
                f"/repos/{owner}/{repo}/issues/{number}/comments?per_page=20",
                operation="GitHub issue comments fetch",
            )
            comments = [
                GitHubIssueComment(
                    id=int(comment.get("id", 0)),
                    user=str((comment.get("user") or {}).get("login", "")),
                    body=str(comment.get("body", "")),
                    html_url=str(comment.get("html_url", "")),
                    created_at=comment.get("created_at"),
                    updated_at=comment.get("updated_at"),
                )
                for comment in comments_payload
                if isinstance(comment, dict)
            ]
        return GitHubIssueInfo(
            task_id=task.id,
            owner=owner,
            repo=repo,
            number=number,
            title=str(issue_payload.get("title", "")),
            body=str(issue_payload.get("body", "")),
            state=str(issue_payload.get("state", "")),
            state_reason=issue_payload.get("state_reason"),
            labels=labels,
            html_url=str(issue_payload.get("html_url", "")),
            comments_count=int(issue_payload.get("comments", 0)),
            comments=comments,
            default_comment=self._build_default_comment(task),
        )

    def create_comment(
        self,
        task_id: str,
        payload: GitHubIssueCommentRequest,
    ) -> GitHubIssueCommentResponse | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        owner, repo, number = self._resolve_issue(task)
        response = _github_json_request(
            f"/repos/{owner}/{repo}/issues/{number}/comments",
            method="POST",
            payload={"body": payload.body},
            require_token=True,
            operation="GitHub issue comment write",
        )
        return GitHubIssueCommentResponse(
            id=int(response.get("id", 0)),
            html_url=str(response.get("html_url", "")),
            body=str(response.get("body", "")),
        )

    def update_state(
        self,
        task_id: str,
        payload: GitHubIssueStateRequest,
    ) -> GitHubIssueStateResponse | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        owner, repo, number = self._resolve_issue(task)
        request_payload: dict[str, Any] = {"state": payload.state}
        if payload.state == "closed":
            request_payload["state_reason"] = payload.state_reason or "completed"
        response = _github_json_request(
            f"/repos/{owner}/{repo}/issues/{number}",
            method="PATCH",
            payload=request_payload,
            require_token=True,
            operation="GitHub issue state update",
        )
        return GitHubIssueStateResponse(
            state=str(response.get("state", "")),
            state_reason=response.get("state_reason"),
            html_url=str(response.get("html_url", "")),
        )

    def update_labels(
        self,
        task_id: str,
        payload: GitHubIssueLabelsRequest,
    ) -> GitHubIssueLabelsResponse | None:
        task = task_service.get_task_record(task_id)
        if task is None:
            return None
        owner, repo, number = self._resolve_issue(task)
        response = _github_json_request(
            f"/repos/{owner}/{repo}/issues/{number}/labels",
            method="PUT",
            payload={"labels": payload.labels},
            require_token=True,
            operation="GitHub issue labels update",
        )
        labels = [
            str(label.get("name"))
            for label in response
            if isinstance(label, dict) and label.get("name")
        ]
        return GitHubIssueLabelsResponse(labels=labels)


github_issue_service = GitHubIssueService()
