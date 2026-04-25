from __future__ import annotations

from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
import sys

from langchain_core.tools import tool


MAX_TOOL_OUTPUT_CHARS = 12000
DEFAULT_READ_END_LINE = 200
DEFAULT_LIST_LIMIT = 200
DEFAULT_SEARCH_LIMIT = 100
DEFAULT_IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "node_modules",
}


def _workspace_root() -> Path:
    return Path.cwd().resolve()


def _assistant_root() -> Path:
    configured = os.getenv("GIT_ISSUE_ASSISTANT_HOME")
    if configured:
        return Path(configured).resolve()
    return _workspace_root()


def _repo_root() -> Path:
    configured = os.getenv("GIT_ISSUE_ASSISTANT_REPO_ROOT")
    if configured:
        return Path(configured).resolve()
    return _workspace_root()


def _resolve_workspace_path(raw_path: str) -> Path:
    root = _repo_root()
    path = Path(raw_path)
    resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError("Path must stay inside the current workspace.")
    return resolved


def _truncate_output(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...<truncated>"


def _is_ignored_path(path: Path) -> bool:
    return any(part in DEFAULT_IGNORED_DIR_NAMES for part in path.parts)


def _format_command_result(result: subprocess.CompletedProcess[str]) -> str:
    parts: list[str] = []
    if result.stdout:
        parts.append(result.stdout.strip())
    if result.stderr:
        parts.append(f"[STDERR]\n{result.stderr.strip()}")
    if not parts:
        parts.append(f"Command finished with exit code {result.returncode}.")
    return _truncate_output("\n".join(part for part in parts if part))


def _run_command(
    command: list[str] | str,
    *,
    cwd: Path | None = None,
    timeout: int = 60,
    shell: bool = False,
) -> str:
    try:
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd or _repo_root()),
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout} seconds."
    except Exception as exc:
        return f"Error executing command: {exc}"
    return _format_command_result(result)


def _read_file_impl(file_path: str, start_line: int = 1, end_line: int = DEFAULT_READ_END_LINE) -> str:
    resolved_path = _resolve_workspace_path(file_path)
    start_line = max(1, int(start_line))
    end_line = max(start_line, int(end_line))

    with resolved_path.open("r", encoding="utf-8") as file:
        lines = file.readlines()

    selected_lines = lines[start_line - 1 : end_line]
    if not selected_lines:
        return f"No content found in {resolved_path} for lines {start_line}-{end_line}."

    result = "".join(f"{start_line + index} | {line}" for index, line in enumerate(selected_lines))
    return _truncate_output(result)


def _list_files_impl(
    path: str = ".",
    recursive: bool = True,
    file_glob: str = "*",
    limit: int = DEFAULT_LIST_LIMIT,
) -> str:
    base_path = _resolve_workspace_path(path)
    iterator = base_path.rglob(file_glob) if recursive else base_path.glob(file_glob)
    files = [item for item in iterator if item.is_file() and not _is_ignored_path(item.relative_to(base_path))]
    files = sorted(files)[: max(1, int(limit))]
    if not files:
        return f"No files matched in {base_path}."
    root = _repo_root()
    return "\n".join(str(item.relative_to(root)) for item in files)


def _search_code_python_fallback(
    pattern: str,
    base_path: Path,
    file_glob: str,
    case_sensitive: bool,
    max_results: int,
) -> str:
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled = re.compile(pattern, flags)
    matches: list[str] = []

    for file_path in sorted(base_path.rglob(file_glob)):
        if not file_path.is_file():
            continue
        if _is_ignored_path(file_path.relative_to(base_path)):
            continue
        try:
            with file_path.open("r", encoding="utf-8") as file:
                for line_number, line in enumerate(file, start=1):
                    if compiled.search(line):
                        matches.append(
                            f"{file_path.relative_to(_repo_root())}:{line_number}: {line.rstrip()}"
                        )
                        if len(matches) >= max_results:
                            return "\n".join(matches)
        except UnicodeDecodeError:
            continue

    return "\n".join(matches) if matches else "No matches found."


def _search_code_impl(
    pattern: str,
    search_path: str = ".",
    file_glob: str = "*",
    case_sensitive: bool = False,
    max_results: int = DEFAULT_SEARCH_LIMIT,
) -> str:
    base_path = _resolve_workspace_path(search_path)
    max_results = max(1, int(max_results))

    if shutil.which("rg"):
        command = [
            "rg",
            "-n",
            "--no-heading",
            "--hidden",
            "--glob",
            file_glob,
            "--glob",
            "!.git/**",
            "--glob",
            "!__pycache__/**",
            "--glob",
            "!.pytest_cache/**",
            "--glob",
            "!.mypy_cache/**",
            "--glob",
            "!.ruff_cache/**",
            "--glob",
            "!.tox/**",
            "--glob",
            "!.venv/**",
            "--glob",
            "!venv/**",
            "--glob",
            "!node_modules/**",
            "--max-count",
            str(max_results),
        ]
        if not case_sensitive:
            command.append("-i")
        command.extend([pattern, str(base_path)])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=str(_repo_root()),
        )
        if result.returncode == 0:
            return _truncate_output(result.stdout.strip())
        if result.returncode == 1:
            return "No matches found."
        stderr = result.stderr.strip() or "Unknown ripgrep error."
        return f"Error searching code.\n[STDERR]\n{stderr}"

    return _truncate_output(
        _search_code_python_fallback(pattern, base_path, file_glob, case_sensitive, max_results)
    )


def _write_file_impl(file_path: str, content: str) -> str:
    resolved_path = _resolve_workspace_path(file_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("w", encoding="utf-8") as file:
        file.write(content)
    return f"Wrote {len(content)} characters to {resolved_path.relative_to(_repo_root())}."


def _replace_in_file_impl(
    file_path: str,
    old_text: str,
    new_text: str,
    replace_all: bool = False,
) -> str:
    resolved_path = _resolve_workspace_path(file_path)
    with resolved_path.open("r", encoding="utf-8") as file:
        content = file.read()

    occurrences = content.count(old_text)
    if occurrences == 0:
        return "Error: old_text was not found in the file."
    if occurrences > 1 and not replace_all:
        return f"Error: old_text matched {occurrences} times. Set replace_all=True or use a more specific snippet."

    updated = content.replace(old_text, new_text, -1 if replace_all else 1)
    with resolved_path.open("w", encoding="utf-8") as file:
        file.write(updated)

    replaced_count = occurrences if replace_all else 1
    return f"Updated {resolved_path.relative_to(_repo_root())}; replaced {replaced_count} occurrence(s)."


def _patch_file_impl(file_path: str, diff_content: str) -> str:
    resolved_path = _resolve_workspace_path(file_path)
    with resolved_path.open("r", encoding="utf-8") as file:
        content = file.read()

    block_pattern = re.compile(
        r"<<<<<<< SEARCH\r?\n(.*?)\r?\n=======\r?\n(.*?)\r?\n>>>>>>> REPLACE",
        re.DOTALL,
    )
    blocks = block_pattern.findall(diff_content)
    if not blocks:
        return (
            "Error: no valid patch blocks found. Use the format:\n"
            "<<<<<<< SEARCH\nold text\n=======\nnew text\n>>>>>>> REPLACE"
        )

    applied = 0
    for old_text, new_text in blocks:
        occurrences = content.count(old_text)
        if occurrences == 0:
            return f"Error: patch block {applied + 1} SEARCH text was not found."
        if occurrences > 1:
            return f"Error: patch block {applied + 1} SEARCH text matched {occurrences} times."
        content = content.replace(old_text, new_text, 1)
        applied += 1

    with resolved_path.open("w", encoding="utf-8") as file:
        file.write(content)

    return f"Applied {applied} patch block(s) to {resolved_path.relative_to(_repo_root())}."


def _current_repo_info_impl() -> str:
    repo_root = _repo_root()
    assistant_root = _assistant_root()
    try:
        relative_repo = repo_root.relative_to(assistant_root)
    except ValueError:
        relative_repo = repo_root
    return (
        f"assistant_root={assistant_root}\n"
        f"repo_root={repo_root}\n"
        f"repo_root_relative={relative_repo}"
    )


def _bash_terminal_impl(command: str, timeout_seconds: int = 60) -> str:
    return _run_command(command, shell=True, timeout=max(1, int(timeout_seconds)))


def _run_pytest_impl(pytest_args: str = "", working_dir: str = ".") -> str:
    resolved_working_dir = _resolve_workspace_path(working_dir)
    command = [sys.executable, "-m", "pytest"]
    if pytest_args.strip():
        command.extend(shlex.split(pytest_args, posix=False))
    return _run_command(command, cwd=resolved_working_dir, timeout=300)


def _git_clone_repo_impl(repo_url: str, target_dir: str, branch: str = "", depth: int = 0) -> str:
    if shutil.which("git") is None:
        return "Error: git is not installed or not available in PATH."

    target_path = Path(target_dir)
    destination = (_assistant_root() / target_path).resolve() if not target_path.is_absolute() else target_path.resolve()
    if destination.exists() and any(destination.iterdir()):
        git_dir = destination / ".git"
        if git_dir.exists():
            return f"Repository already exists at {destination}. Reuse the existing local copy instead of cloning again."
        return f"Error: target directory already exists and is not empty: {destination}"

    destination.parent.mkdir(parents=True, exist_ok=True)

    command = ["git", "clone"]
    if branch:
        command.extend(["--branch", branch])
    if int(depth) > 0:
        command.extend(["--depth", str(int(depth))])
    command.extend([repo_url, str(destination)])
    return _run_command(command, timeout=300)


def _git_status_impl(repo_path: str = ".") -> str:
    resolved_repo_path = _resolve_workspace_path(repo_path)
    return _run_command(["git", "status", "--short"], cwd=resolved_repo_path, timeout=60)


def _git_diff_impl(repo_path: str = ".", staged: bool = False) -> str:
    resolved_repo_path = _resolve_workspace_path(repo_path)
    command = ["git", "diff"]
    if staged:
        command.append("--staged")
    return _run_command(command, cwd=resolved_repo_path, timeout=60)

def _git_add_impl(file_paths: list[str] | str = ".") -> str:
    """Add files to staging area."""
    if shutil.which("git") is None:
        return "Error: git is not installed or not available in PATH."
    
    # 处理参数
    if isinstance(file_paths, list):
        paths = file_paths
    else:
        paths = [file_paths]
    
    command = ["git", "add"] + paths
    return _run_command(command, cwd=_repo_root(), timeout=30)

def _git_commit_impl(message: str, all_changes: bool = True) -> str:
    """Commit staged changes."""
    if shutil.which("git") is None:
        return "Error: git is not installed or not available in PATH."
    
    command = ["git", "commit"]
    if all_changes:
        command.append("-a")  # 自动暂存所有已跟踪文件的修改
    command.extend(["-m", message])
    
    result = _run_command(command, cwd=_repo_root(), timeout=30)
    
    # 如果没有需要提交的内容，返回友好提示
    if "nothing to commit" in result.lower():
        return "Nothing to commit - working tree clean."
    return result

def _git_push_impl(
    remote: str = "origin",
    branch: str = "",
    force: bool = False,
    set_upstream: bool = False,
    timeout_seconds: int = 120,
) -> str:
    """Push local commits to remote repository."""
    if shutil.which("git") is None:
        return "Error: git is not installed or not available in PATH."

    if not branch:
        # 获取当前分支
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(_repo_root()),
                timeout=10,
            )
            if result.returncode != 0:
                return f"Error: failed to get current branch: {result.stderr.strip()}"
            branch = result.stdout.strip()
        except subprocess.TimeoutExpired:
            return "Error: timed out while getting current branch."
        except Exception as exc:
            return f"Error: {exc}"

    command = ["git", "push"]
    
    if force:
        command.append("--force")
    
    command.append(remote)
    command.append(branch)
    
    if set_upstream:
        command.append("--set-upstream")
    
    return _run_command(command, timeout=timeout_seconds, cwd=_repo_root())

@tool
def list_files(
    path: str = ".",
    recursive: bool = True,
    file_glob: str = "*",
    limit: int = DEFAULT_LIST_LIMIT,
) -> str:
    """List files inside the workspace, optionally recursively and filtered by glob."""
    return _list_files_impl(path, recursive, file_glob, limit)


@tool
def read_file(
    file_path: str,
    start_line: int = 1,
    end_line: int = DEFAULT_READ_END_LINE,
) -> str:
    """Read a file from the workspace and return its contents with line numbers."""
    return _read_file_impl(file_path, start_line, end_line)


@tool
def search_code(
    pattern: str,
    search_path: str = ".",
    file_glob: str = "*",
    case_sensitive: bool = False,
    max_results: int = DEFAULT_SEARCH_LIMIT,
) -> str:
    """Search code by regex pattern across files in the workspace."""
    return _search_code_impl(pattern, search_path, file_glob, case_sensitive, max_results)


@tool
def write_file(file_path: str, content: str) -> str:
    """Create or overwrite a file inside the workspace with the given content."""
    return _write_file_impl(file_path, content)


@tool
def replace_in_file(
    file_path: str,
    old_text: str,
    new_text: str,
    replace_all: bool = False,
) -> str:
    """Replace exact text in a file; refuses ambiguous multi-match replacements unless replace_all=True."""
    return _replace_in_file_impl(file_path, old_text, new_text, replace_all)


@tool
def patch_file(file_path: str, diff_content: str) -> str:
    """Apply SEARCH/REPLACE patch blocks to a file using the format <<<<<<< SEARCH / ======= / >>>>>>> REPLACE."""
    return _patch_file_impl(file_path, diff_content)


@tool
def bash_terminal(command: str, timeout_seconds: int = 60) -> str:
    """Run a shell command in the workspace. Use this for builds, scripts, and one-off diagnostics."""
    return _bash_terminal_impl(command, timeout_seconds)


@tool
def run_pytest(pytest_args: str = "", working_dir: str = ".") -> str:
    """Run pytest from the workspace or a subdirectory and return the test output."""
    return _run_pytest_impl(pytest_args, working_dir)


@tool
def git_clone_repo(repo_url: str, target_dir: str, branch: str = "", depth: int = 0) -> str:
    """Clone a Git repository into a local directory within the current workspace."""
    return _git_clone_repo_impl(repo_url, target_dir, branch, depth)


@tool
def git_status(repo_path: str = ".") -> str:
    """Show git status for a repository inside the workspace."""
    return _git_status_impl(repo_path)


@tool
def git_diff(repo_path: str = ".", staged: bool = False) -> str:
    """Show git diff for a repository inside the workspace."""
    return _git_diff_impl(repo_path, staged)


@tool
def current_repo_info() -> str:
    """Return the assistant root and the current repository root. Use this before path-sensitive operations if needed."""
    return _current_repo_info_impl()

@tool
def git_add(file_paths: str = ".") -> str:
    """
    Add files to staging area.
    
    Args:
        file_paths: Space-separated file paths, or "." for all changes
    """
    paths = file_paths.split() if file_paths != "." else ["."]
    return _git_add_impl(paths)

@tool
def git_commit(message: str) -> str:
    """
    Commit staged changes with a message.
    
    Args:
        message: Commit message describing the changes
    """
    return _git_commit_impl(message)


@tool
def git_push(
    remote: str = "origin",
    branch: str = "",
    force: bool = False,
    set_upstream: bool = False,
    timeout_seconds: int = 120,
) -> str:
    """
    Push local commits to remote repository.
    
    Args:
        remote: Remote name to push to (default: "origin")
        branch: Branch name to push (default: current branch)
        force: Force push, use with caution (default: False)
        set_upstream: Set upstream for the branch (default: False)
        timeout_seconds: Maximum execution time in seconds (default: 120)
    """
    return _git_push_impl(remote, branch, force, set_upstream, timeout_seconds)

AGENT_TOOLS = [
    current_repo_info,
    list_files,
    read_file,
    search_code,
    write_file,
    replace_in_file,
    patch_file,
    bash_terminal,
    run_pytest,
    git_clone_repo,
    git_status,
    git_diff,
    git_add,
    git_commit,
    git_push,
]
