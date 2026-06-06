from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GitDiffResult:
    repo_path: str
    branch: str = ""
    status: str = ""
    diff: str = ""
    has_changes: bool = False


@dataclass(frozen=True)
class GitPushResult:
    repo_path: str
    commit_hash: str | None = None
    pushed: bool = False
    output: str = ""


@dataclass(frozen=True)
class GitPullRequestResult:
    repo_path: str
    branch: str
    base_branch: str
    commit_hash: str | None = None
    pr_url: str | None = None
    output: str = ""
