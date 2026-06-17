from __future__ import annotations

from pathlib import Path
import locale
import os
import re
import shlex
import shutil
import subprocess
import sys

from langchain_core.tools import tool

# ---------- 沙箱透明路由（迭代三第二组新增）----------
# 当沙箱激活时，_run_command() 自动将 shell 命令路由到 Docker 容器执行
_active_sandbox = None  # DockerSandbox | None


def set_active_sandbox(sandbox) -> None:
    """设置当前活跃的 Docker 沙箱。调用后，所有 shell 工具将透明路由到容器。

    由 orchestrator._node_h_planner 在会话首次规划时调用。
    """
    global _active_sandbox
    _active_sandbox = sandbox


def clear_active_sandbox() -> None:
    """清除当前活跃的沙箱引用。工具回退到宿主直接执行。"""
    global _active_sandbox
    _active_sandbox = None


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
    root = _repo_root().resolve()
    cleaned_path = str(raw_path).strip().strip("\"'")
    path = Path(cleaned_path)
    if path.anchor and not path.drive and cleaned_path.startswith(("/", "\\")):
        path = Path(cleaned_path.lstrip("/\\"))
    resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError(
            "Path must stay inside the current workspace. "
            f"raw_path={raw_path!r}, repo_root={root}, resolved={resolved}"
        )
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
    if result.returncode != 0:
        parts.append(f"Command finished with exit code {result.returncode}.")
    elif not parts:
        parts.append(f"Command finished with exit code {result.returncode}.")
    return _truncate_output("\n".join(part for part in parts if part))


def _decode_process_output(data: bytes | None) -> str:
    if not data:
        return ""

    encodings = ["utf-8", locale.getpreferredencoding(False), "gbk", "cp936"]
    seen: set[str] = set()
    for encoding in encodings:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")


def _run_command(
    command: list[str] | str,
    *,
    cwd: Path | None = None,
    timeout: int = 60,
    shell: bool = False,
) -> str:
    """在仓库中执行命令。当沙箱激活时，透明路由到 Docker 容器执行。

    路由逻辑：
      - 若 _active_sandbox 存在且容器已启动 → sandbox.exec_command()
      - 否则 → subprocess.run()（宿主直接执行）

    沙箱模式下，cwd 会被映射为容器内路径；宿主模式下使用原始路径。
    """
    # 将命令统一为字符串（shell=True 时 command 已经是字符串）
    if isinstance(command, list):
        # 使用 shlex.join() 而非 " ".join()，确保含空格/中文的参数被正确引号
        # 例如 git commit -m "fix: 修复 bug" → git commit -m 'fix: 修复 bug'
        command_str = shlex.join(command)
    else:
        command_str = str(command)

    sandbox = _active_sandbox
    if sandbox is not None and sandbox._started:
        # ---- 沙箱模式 ----
        # 将宿主机 Python 路径替换为容器内的 python，修复 run_pytest 的 sys.executable 问题
        # 例如 D:\miniconda\envs\gia\python.exe → python
        command_str = command_str.replace(sys.executable, "python")

        # 将宿主 cwd 映射为容器内路径，并在命令前添加 cd
        try:
            sandbox_cwd = sandbox.path_to_container(str(cwd or _repo_root()))
        except Exception:
            # 路径不在沙箱内，回退到容器 /workspace/repo
            sandbox_cwd = "/workspace/repo"

        # 构造容器内执行的完整命令：cd 到目标目录 → 执行原命令
        container_command = f"cd {sandbox_cwd} && {command_str}"

        try:
            output = sandbox.exec_command(container_command, timeout=timeout)
            # 解析退出码：sandbox.exec_command 在末尾附加了 [EXIT_CODE: N]
            exit_match = re.search(r"\[EXIT_CODE:\s*(\d+)\]\s*$", output)
            if exit_match:
                exit_code = int(exit_match.group(1))
                # 移除 [EXIT_CODE: ...] 后缀，保持输出整洁
                output_clean = output[: exit_match.start()].strip()
            else:
                exit_code = 0
                output_clean = output.strip()

            # 模拟 subprocess.CompletedProcess 的格式
            parts = [output_clean] if output_clean else []
            if exit_code != 0:
                parts.append(f"Command finished with exit code {exit_code}.")
            return _truncate_output("\n".join(parts))

        except Exception as exc:
            # sandbox 中发生的所有异常（SandboxError, TimeoutExpired 等）
            return f"Error executing command in sandbox: {exc}"

    else:
        # ---- 宿主模式 ----
        try:
            result = subprocess.run(
                command_str if shell else command,
                shell=shell,
                capture_output=True,
                timeout=timeout,
                cwd=str(cwd or _repo_root()),
            )
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout} seconds."
        except Exception as exc:
            return f"Error executing command: {exc}"
        result = subprocess.CompletedProcess(
            args=result.args,
            returncode=result.returncode,
            stdout=_decode_process_output(result.stdout),
            stderr=_decode_process_output(result.stderr),
        )
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
            cwd=str(_repo_root()),
        )
        stdout = _decode_process_output(result.stdout)
        stderr = _decode_process_output(result.stderr)
        if result.returncode == 0:
            return _truncate_output(stdout.strip())
        if result.returncode == 1:
            return "No matches found."
        stderr = stderr.strip() or "Unknown ripgrep error."
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


def _new_file_diff(repo_path: Path, relative_path: str, max_bytes: int = 200_000) -> str:
    relative_path = relative_path.strip()
    if not relative_path or _is_ignored_path(Path(relative_path)):
        return ""

    file_path = (repo_path / relative_path).resolve()
    try:
        file_path.relative_to(repo_path.resolve())
    except ValueError:
        return ""
    if not file_path.is_file():
        return ""

    data = file_path.read_bytes()
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
    lines = text.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    trailing = "\n" if body else ""
    return (
        f"diff --git a/{relative_path} b/{relative_path}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{relative_path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}{trailing}"
    )


def _build_untracked_diff(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        timeout=30,
        cwd=str(repo_path),
    )
    stdout = _decode_process_output(result.stdout)
    stderr = _decode_process_output(result.stderr)
    if result.returncode != 0:
        stderr = stderr.strip() or stdout.strip() or "Unknown git error."
        return f"Error listing untracked files.\n[STDERR]\n{stderr}"

    parts = [
        diff
        for line in stdout.splitlines()
        if (diff := _new_file_diff(repo_path, line))
    ]
    return "\n".join(parts)


def _git_diff_impl(repo_path: str = ".", staged: bool = False) -> str:
    resolved_repo_path = _resolve_workspace_path(repo_path)
    command = ["git", "diff"]
    if staged:
        command.append("--staged")
    result = subprocess.run(
        command,
        capture_output=True,
        timeout=60,
        cwd=str(resolved_repo_path),
    )
    stdout = _decode_process_output(result.stdout)
    stderr = _decode_process_output(result.stderr)
    if result.returncode != 0:
        return _format_command_result(
            subprocess.CompletedProcess(
                args=result.args,
                returncode=result.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        )

    parts = [stdout.strip()]
    if not staged:
        parts.append(_build_untracked_diff(resolved_repo_path).strip())

    diff = "\n".join(part for part in parts if part)
    return _truncate_output(diff or "Command finished with exit code 0.")

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
                cwd=str(_repo_root()),
                timeout=10,
            )
            stdout = _decode_process_output(result.stdout)
            stderr = _decode_process_output(result.stderr)
            if result.returncode != 0:
                return f"Error: failed to get current branch: {stderr.strip()}"
            branch = stdout.strip()
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
]

# 全部工具列表（含 git_add/git_commit/git_push），供 ToolRegistry 注册用。
# Agent 通过 AGENT_TOOLS 使用受限子集；git_add/git_commit/git_push 由 CLI 直接调用。
AGENT_TOOLS_ALL = AGENT_TOOLS + [
    git_add,
    git_commit,
    git_push,
]

