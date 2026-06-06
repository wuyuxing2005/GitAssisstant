from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .git import run_git_capture


def parse_github_remote_url(remote_url: str) -> tuple[str, str] | None:
    patterns = (
        r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?/?$",
        r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.search(pattern, remote_url)
        if match:
            return match.group("owner"), match.group("repo").removesuffix(".git")
    return None


def parse_github_remote(repo_path: str, remote: str = "origin") -> tuple[str, str] | None:
    remote_url = run_git_capture(repo_path, ["config", "--get", f"remote.{remote}.url"]).strip()
    return parse_github_remote_url(remote_url)


def create_github_pr(
    repo_path: str,
    branch: str,
    base_branch: str,
    title: str,
    body: str,
    *,
    remote: str = "origin",
) -> str:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 GITHUB_TOKEN，无法创建 PR。")
    repo_info = parse_github_remote(repo_path, remote=remote)
    if repo_info is None:
        raise RuntimeError(f"当前 {remote} 不是可识别的 GitHub 仓库，无法创建 PR。")
    owner, repo = repo_info

    payload = json.dumps({
        "title": title,
        "body": body,
        "head": branch,
        "base": base_branch,
    }).encode("utf-8")
    request = Request(
        f"https://api.github.com/repos/{owner}/{repo}/pulls",
        data=payload,
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
            data = json.loads(response.read().decode("utf-8"))
            return data.get("html_url", "")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"创建 PR 失败: HTTP {exc.code} {detail}") from exc

