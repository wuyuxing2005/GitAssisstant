from fastapi import APIRouter, HTTPException, Query

from gitIssueAssitant.core.schemas.task import GitHubIssueSummary
from gitIssueAssitant.core.services.github_issue_service import (
    GitHubIssueError,
    _parse_github_remote,
    _parse_repo_source,
    github_issue_service,
)

router = APIRouter()


def _resolve_owner_repo(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL or owner/repo string."""
    remote_info = _parse_github_remote(url)
    if remote_info is not None:
        return remote_info

    repo_info = _parse_repo_source(url)
    if repo_info is not None:
        return repo_info

    raise ValueError(f"无法从输入中解析出 GitHub owner/repo: {url}")


@router.get(
    "/repos/issues",
    response_model=list[GitHubIssueSummary],
    summary="列出指定仓库的 GitHub Issues",
)
def list_repo_issues(
    url: str = Query(..., description="GitHub 仓库地址，例如 https://github.com/org/repo.git 或 org/repo"),
    state: str = Query(default="open", description="Issue 状态: open, closed, all"),
    per_page: int = Query(default=30, ge=1, le=100, description="每页数量"),
) -> list[GitHubIssueSummary]:
    try:
        owner, repo = _resolve_owner_repo(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return github_issue_service.list_issues(owner, repo, state=state, per_page=per_page)
    except GitHubIssueError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

