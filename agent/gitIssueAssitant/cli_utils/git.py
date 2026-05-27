from __future__ import annotations

from pathlib import Path
import re
import subprocess


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


def run_git_capture(repo_path: str, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return (result.stdout or "") + (result.stderr or "")


def _untracked_file_diff(repo_path: str, relative_path: str) -> str:
    if is_temporary_file(relative_path):
        return ""
    full_path = Path(repo_path) / relative_path
    if not full_path.is_file():
        return ""
    data = full_path.read_bytes()
    if b"\0" in data:
        return ""
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


def working_tree_diff_for_commit(repo_path: str) -> str:
    parts = [
        run_git_capture(repo_path, ["diff", "--no-ext-diff", "--binary"]),
        run_git_capture(repo_path, ["diff", "--no-ext-diff", "--binary", "--cached"]),
    ]
    status = run_git_capture(repo_path, ["status", "--porcelain", "--untracked-files=all"])
    for line in status.splitlines():
        if not line.startswith("?? "):
            continue
        relative_path = line[3:].strip().strip('"')
        untracked_diff = _untracked_file_diff(repo_path, relative_path)
        if untracked_diff:
            parts.append(untracked_diff)
    return "\n".join(part for part in parts if part.strip())
