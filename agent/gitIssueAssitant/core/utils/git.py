from __future__ import annotations

import re
import subprocess
from pathlib import Path


def is_temporary_file(file_path: str) -> bool:
    path = Path(file_path)
    ignored_parts = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    return any(part in ignored_parts for part in path.parts) or path.suffix == ".pyc"


def extract_modified_files_from_diff(diff: str) -> list[str]:
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git a/"):
            match = re.search(r"a/(.+?) b/", line)
            if match:
                file_path = match.group(1)
                if file_path not in files and not is_temporary_file(file_path):
                    files.append(file_path)
    return files


def run_git_command(
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


def run_git_capture(repo_path: str | Path, args: list[str]) -> str:
    return run_git_command(repo_path, args, timeout=60, check=False)


def is_git_repo(repo_path: str | Path) -> bool:
    try:
        run_git_command(repo_path, ["rev-parse", "--show-toplevel"], timeout=10)
    except Exception:
        return False
    return True


def _untracked_file_diff(repo_path: str | Path, relative_path: str, max_bytes: int = 200_000) -> str:
    if is_temporary_file(relative_path):
        return ""
    full_path = Path(repo_path) / relative_path
    if not full_path.is_file():
        return ""
    data = full_path.read_bytes()
    if b"\0" in data:
        return (
            f"diff --git a/{relative_path} b/{relative_path}\n"
            "new file mode 100644\n"
            f"Binary files /dev/null and b/{relative_path} differ\n"
        )
    if len(data) > max_bytes:
        return (
            f"diff --git a/{relative_path} b/{relative_path}\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            f"+++ b/{relative_path}\n"
            "@@\n"
            f"+[new file omitted: {len(data)} bytes]\n"
        )
    text = data.decode("utf-8", errors="replace")
    lines = "".join(f"+{line}" for line in text.splitlines(keepends=True))
    if text and not text.endswith(("\n", "\r")):
        lines += "\n\\ No newline at end of file\n"
    return (
        f"diff --git a/{relative_path} b/{relative_path}\n"
        "new file mode 100644\n"
        "index 0000000..0000000\n"
        "--- /dev/null\n"
        f"+++ b/{relative_path}\n"
        "@@ -0,0 +1 @@\n"
        f"{lines}"
    )


def build_untracked_diff(repo_path: str | Path) -> str:
    output = run_git_command(
        repo_path,
        ["ls-files", "--others", "--exclude-standard"],
        timeout=30,
    )
    parts = [
        diff
        for line in output.splitlines()
        if (diff := _untracked_file_diff(repo_path, line.strip()))
    ]
    return "\n".join(parts)


def git_status_short(repo_path: str | Path) -> str:
    return run_git_command(repo_path, ["status", "--short"], timeout=30)


def current_git_branch(repo_path: str | Path) -> str:
    return run_git_command(
        repo_path,
        ["rev-parse", "--abbrev-ref", "HEAD"],
        timeout=10,
    ).strip()


def working_tree_diff_for_commit(repo_path: str | Path) -> str:
    parts = [
        run_git_command(repo_path, ["diff", "--no-ext-diff", "--binary"], timeout=60),
        run_git_command(
            repo_path,
            ["diff", "--no-ext-diff", "--binary", "--cached"],
            timeout=60,
        ),
        build_untracked_diff(repo_path),
    ]
    return "\n".join(part for part in parts if part.strip())

