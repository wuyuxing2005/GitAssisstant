# sandbox.py
"""
Docker 沙箱模块
负责为每个 Issue 修复任务创建独立的 Docker 容器，
所有文件读写、命令执行、测试执行均在容器内完成。
"""

from __future__ import annotations


import os
import subprocess
import uuid
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

import yaml  # 需要安装 pyyaml

# ---------- 默认配置 ----------
DEFAULT_SANDBOX_CONFIG = {
    "image": "python:3.11",
    "working_dir": ".",
    "install": [],
    "test": ["pytest"],
    "lint": [],
    "timeout_seconds": 300,
    "allow_network": False,
}

# ---------- 自定义异常 ----------
class SandboxError(Exception):
    """沙箱相关错误"""


def _docker_not_found_message() -> str:
    return (
        "未找到 Docker 命令：后端进程的 PATH 中没有 docker.exe。"
        "请确认 Docker Desktop 已安装并启动；如果已安装，请把 Docker CLI 目录加入 PATH，例如 "
        r"C:\Program Files\Docker\Docker\resources\bin，然后重启后端服务。"
    )


# ---------- 沙箱配置加载 ----------
def load_sandbox_config(repo_path: Path) -> Dict[str, Any]:
    """
    从仓库根目录加载 .agent-sandbox.yml。
    若文件不存在，抛出 SandboxError 并提示用户创建。
    """
    config_path = repo_path / ".agent-sandbox.yml"
    if not config_path.exists():
        raise SandboxError(
            f"仓库缺少沙箱配置文件: {config_path}\n"
            "请在仓库根目录创建 .agent-sandbox.yml，参考格式见文档。"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    # 合并默认值
    merged = DEFAULT_SANDBOX_CONFIG.copy()
    merged.update(config)
    return merged


# ---------- Docker 沙箱管理器 ----------
class DockerSandbox:
    """
    为单个任务管理的 Docker 沙箱。

    使用方式：
        sandbox = DockerSandbox(task_id="task-001", repo_path=Path("/path/to/repo"))
        sandbox.start()
        result = sandbox.exec_command("pytest tests/test_example.py")
        print(result)
        sandbox.stop()
        sandbox.cleanup()
    """

    def __init__(
        self,
        task_id: str,
        repo_path: Path,
        workspace_root: Optional[Path] = None,
    ):
        """
        :param task_id: 唯一任务 ID，用于隔离工作目录
        :param repo_path: 宿主机上原始仓库路径
        :param workspace_root: 沙箱工作区根目录，默认为 ./workspaces
        """
        self.task_id = task_id
        self.repo_path = repo_path.resolve()
        self.workspace_root = (workspace_root or Path.cwd() / "workspaces").resolve()
        self.host_work_dir = self.workspace_root / task_id / "repo"
        self.config: Dict[str, Any] = {}
        self.container_name = f"sandbox-{task_id}-{uuid.uuid4().hex[:8]}"
        self._started = False

    def _image_exists(self, image: str) -> bool:
        """检查本地是否已有镜像"""
        if shutil.which("docker") is None:
            raise SandboxError(_docker_not_found_message())
        result = subprocess.run(
            ["docker", "images", "-q", image],
            capture_output=True, text=True
        )
        return bool(result.stdout.strip())
    
    def _pull_image_with_fallback(self, image: str, timeout: int = 120) -> str:
        """
        拉取镜像，支持回退策略：先尝试官方名，若失败则尝试国内常用镜像源前缀。
        返回最终使用的镜像名称。
        """
        # 1. 先检查本地是否已有
        if self._image_exists(image):
            print(f"[sandbox.py] 本地已存在镜像: {image}")
            return image

        # 2. 尝试直接拉取
        print(f"[sandbox.py] 本地未找到镜像，尝试直接拉取: {image}")
        try:
            self._run_docker_command(["pull", image], timeout=timeout)
            print(f"[sandbox.py] 镜像 {image} 拉取成功")
            return image
        except SandboxError as e:
            print(f"[sandbox.py] 直接拉取失败: {e}")

        # 3. 回退：尝试带国内镜像源前缀的地址
        fallback_prefixes = [
            "docker.m.daocloud.io/library/",
            "dockerhub.timeweb.cloud/library/",
            "mirror.ccs.tencentyun.com/library/",
        ]
        # 如果 image 已经是带域名的完整地址，则不再添加前缀
        if "/" in image:
            print("[sandbox.py] 镜像名已含域名，不再尝试其他源")
            

        for prefix in fallback_prefixes:
            fallback_image = f"{prefix}{image}"
            print(f"[sandbox.py] 尝试回退镜像: {fallback_image}")
            try:
                self._run_docker_command(["pull", fallback_image], timeout=300)
                print(f"[sandbox.py] 镜像 {fallback_image} 拉取成功")
                # 关键：拉取后，为后续使用添加本地 tag，使 image 指向刚拉取的镜像
                self._run_docker_command(["tag", fallback_image, image])
                return image
            except SandboxError:
                continue

        raise SandboxError(
            f"无法拉取镜像 {image}，所有源均不可用。\n"
            "请检查网络连接，或手动拉取镜像后重试。"
        )
    
    def load_config(self):
        """从仓库加载 .agent-sandbox.yml 配置"""
        self.config = load_sandbox_config(self.repo_path)
        print(f"[sandbox.py] 已加载沙箱配置: image={self.config['image']}")

    def prepare_workspace(self):
        """在宿主机上创建独立的工作副本，并将仓库内容复制进去"""
        if self.host_work_dir.exists():
            import shutil
            shutil.rmtree(self.host_work_dir)
        self.host_work_dir.mkdir(parents=True, exist_ok=True)

        # 复制仓库文件到工作目录（排除 .git 以减小体积，但保留 .git 以便 git 操作）
        # 注意：若需保留 git 历史，可完整复制，但可能较大；此处选择保留 .git
        import shutil
        shutil.copytree(self.repo_path, self.host_work_dir, symlinks=True, dirs_exist_ok=True)
        print(f"[sandbox.py] 工作目录已创建: {self.host_work_dir}")


    def start(self):
        """
        启动 Docker 容器：
        - 拉取镜像（如无本地）
        - 创建容器并挂载工作目录
        - 执行 install 命令
        - 容器保持运行，供后续 exec 使用
        """
        self.load_config()
        self.prepare_workspace()

        image = self.config["image"]
        allow_network = self.config.get("allow_network", False)

        # 1. 确保镜像存在
        # self._run_docker_command(["pull", image], timeout=120)
        image = self._pull_image_with_fallback(image, timeout=300)

        # 2. 创建容器（挂载整个 workspace 目录）
        mount_src = str(self.host_work_dir.parent)  # 挂载 task_id 目录
        mount_dst = "/workspace"
        container_args = [
            "run", "-d",                     # 后台运行
            "--name", self.container_name,
            "-v", f"{mount_src}:{mount_dst}",
            "-w", "/workspace/repo",        # 工作目录为仓库根
            "--cpus", "2",                   # CPU 限制
            "--memory", "2g",                # 内存限制
            "--network", "none" if not allow_network else "bridge",
            "--rm",                          # 容器停止后自动删除
        ]
        # 可以添加更多安全限制，如 --cap-drop=ALL
        container_args.append(image)
        container_args.extend(["sleep", "infinity"])  # 保持容器运行

        result_output = self._run_docker_command(container_args, timeout=60)
        # 检查容器是否成功创建（通过输出中的 EXIT_CODE 标记或检查容器是否存在）
        if "[EXIT_CODE: 0]" not in result_output:
            # 如果失败，清理并抛出异常
            raise SandboxError(f"容器创建失败: {result_output}")
        self._started = True
        print(f"[sandbox.py] 容器已启动: {self.container_name}")

        # 3. 执行安装命令
        install_cmds = self.config.get("install", [])
        for cmd in install_cmds:
            print(f"[sandbox.py] 执行安装命令: {cmd}")
            result = self.exec_command(cmd, timeout=300)
            print(f"[sandbox.py] 安装输出:\n{result}")

    def exec_command(self, command: str, timeout: Optional[int] = None) -> str:
        """
        在沙箱容器内执行命令并返回输出。
        :param command: 要执行的命令字符串
        :param timeout: 超时秒数，默认使用配置文件中的 timeout_seconds
        """
        if not self._started:
            raise SandboxError("沙箱尚未启动，请先调用 start()")
        if timeout is None:
            timeout = self.config.get("timeout_seconds", 300)

        # 使用 docker exec 执行命令
        exec_args = ["exec", self.container_name, "bash", "-c", command]
        return self._run_docker_command(exec_args, timeout=timeout)

    def stop(self):
        """停止并删除容器"""
        if not self._started:
            return
        try:
            self._run_docker_command(["stop", self.container_name], timeout=10)
            print(f"[sandbox.py] 容器已停止: {self.container_name}")
        except Exception as e:
            print(f"[sandbox.py] 停止容器时出错: {e}")
        self._started = False

    def cleanup(self):
        """清理宿主机工作目录"""
        import shutil
        if self.host_work_dir.exists():
            shutil.rmtree(self.host_work_dir)
            print(f"[sandbox.py] 工作目录已清理: {self.host_work_dir}")

    # def _run_docker_command(self, args: list, timeout: int = 60) -> str:
    #     """底层执行 docker 命令"""
    #     cmd = ["docker"] + args
    #     print(f"[sandbox.py] 执行 Docker 命令: {' '.join(cmd)}")
    #     try:
    #         result = subprocess.run(
    #             cmd,
    #             capture_output=True,
    #             text=True,
    #             timeout=timeout,
    #             check=False,
    #         )
    #         if result.returncode != 0 and "stop" not in args:  # stop 可能返回非零
    #             error_msg = result.stderr.strip() or result.stdout.strip()
    #             raise SandboxError(f"Docker 命令失败: {' '.join(cmd)}\n{error_msg}")
    #         output = result.stdout.strip()
    #         if result.stderr.strip():
    #             output += "\n[STDERR]\n" + result.stderr.strip()
    #         return output
    #     except subprocess.TimeoutExpired:
    #         raise SandboxError(f"Docker 命令超时 ({timeout}s): {' '.join(cmd)}")
    #     except FileNotFoundError:
    #         raise SandboxError("未找到 Docker 命令，请确认 Docker 已安装并在 PATH 中。")
    # def _run_docker_command(self, args: list, timeout: int = 60) -> str:
    #     """底层执行 docker 命令，清除代理环境变量，避免 Docker 使用不可达的内部代理。"""
    #     cmd = ["docker"] + args
    #     print(f"[sandbox.py] 执行 Docker 命令: {' '.join(cmd)}")

    #     # 构造无代理的环境变量
    #     env = os.environ.copy()
    #     for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    #                     "http_proxy", "https_proxy", "no_proxy"]:
    #         env.pop(proxy_var, None)

    #     try:
    #         result = subprocess.run(
    #             cmd,
    #             capture_output=True,
    #             text=True,
    #             timeout=timeout,
    #             env=env,               # 使用清理后的环境
    #             check=False,
    #         )
    #         if result.returncode != 0 and "stop" not in args:
    #             error_msg = result.stderr.strip() or result.stdout.strip()
    #             raise SandboxError(f"Docker 命令失败: {' '.join(cmd)}\n{error_msg}")
    #         output = result.stdout.strip()
    #         if result.stderr.strip():
    #             output += "\n[STDERR]\n" + result.stderr.strip()
    #         return output
    #     except subprocess.TimeoutExpired:
    #         raise SandboxError(f"Docker 命令超时 ({timeout}s): {' '.join(cmd)}")
    #     except FileNotFoundError:
    #         raise SandboxError("未找到 Docker 命令，请确认 Docker 已安装并在 PATH 中。")
    # def _run_docker_command(self, args: list, timeout: int = 60) -> str:
    #     """执行 Docker 命令，实时输出到终端，并返回完整输出。"""
    #     cmd = ["docker"] + args
    #     print(f"\n[sandbox.py] >>> 执行 Docker 命令: {' '.join(cmd)}")

    #     # 清理代理环境变量（同之前）
    #     env = os.environ.copy()
    #     for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    #                     "http_proxy", "https_proxy", "no_proxy"]:
    #         env.pop(proxy_var, None)

    #     try:
    #         # 使用 Popen 以便逐行读取
    #         process = subprocess.Popen(
    #             cmd,
    #             stdout=subprocess.PIPE,
    #             stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout，便于统一读取
    #             text=True,
    #             env=env,
    #             bufsize=1,                 # 行缓冲
    #         )

    #         output_lines = []
    #         start_time = time.time()

    #         # 逐行读取，直到超时或进程结束
    #         while True:
    #             # 检查是否超时
    #             elapsed = time.time() - start_time
    #             if elapsed >= timeout:
    #                 process.kill()
    #                 raise subprocess.TimeoutExpired(cmd, timeout)

    #             # 尝试读取一行，设置短暂的超时（0.1秒）避免死等
    #             try:
    #                 line = process.stdout.readline()
    #             except Exception:
    #                 break

    #             if not line and process.poll() is not None:
    #                 break

    #             if line:
    #                 # 实时打印（不加换行，因为 line 已包含）
    #                 print(f"  {line.rstrip()}")
    #                 output_lines.append(line)

    #         # 等待进程完全结束
    #         process.wait(timeout=5)

    #         # 收集剩余可能未读的输出
    #         remaining = process.stdout.read()
    #         if remaining:
    #             print(f"  {remaining.rstrip()}")
    #             output_lines.append(remaining)

    #         full_output = "".join(output_lines).strip()

    #         if process.returncode != 0 and "stop" not in args:
    #             error_msg = full_output or "命令执行失败，无输出"
    #             raise SandboxError(f"Docker 命令失败: {' '.join(cmd)}\n{error_msg}")

    #         print(f"[sandbox.py] <<< 命令执行完成 (exit code: {process.returncode})")
    #         return full_output

    #     except subprocess.TimeoutExpired:
    #         raise SandboxError(f"Docker 命令超时 ({timeout}s): {' '.join(cmd)}")
    #     except FileNotFoundError:
    #         raise SandboxError("未找到 Docker 命令，请确认 Docker 已安装并在 PATH 中。")
    def _run_docker_command(self, args: list, timeout: int = 60) -> str:
        """执行 Docker 命令，返回完整输出（含 stderr），并在末尾附加退出码。不再因非零退出码抛异常。"""
        cmd = ["docker"] + args
        print(f"[sandbox.py] 执行 Docker 命令: {' '.join(cmd)}")

        env = os.environ.copy()
        for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                        "http_proxy", "https_proxy", "no_proxy"]:
            env.pop(proxy_var, None)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',        # 强制 UTF-8 编码
                errors='replace',        # 无法解码的字符用 � 替换
                timeout=timeout,
                env=env,
                check=False,
            )
            # 合并 stdout 和 stderr
            output = result.stdout.strip()
            if result.stderr.strip():
                output += "\n[STDERR]\n" + result.stderr.strip()
            # 附加退出码信息，方便调用者判断
            output += f"\n[EXIT_CODE: {result.returncode}]"
            print(f"[sandbox.py] 命令完成，退出码: {result.returncode}")
            return output
        except subprocess.TimeoutExpired:
            raise SandboxError(f"Docker 命令超时 ({timeout}s): {' '.join(cmd)}")
        except FileNotFoundError:
            raise SandboxError(_docker_not_found_message())

    # ---------- 路径映射 ----------

    def path_to_container(self, host_path: str | Path) -> str:
        """将宿主机路径映射为容器内路径。

        宿主机工作区结构：
            {workspace_root}/{task_id}/repo/   ← host_work_dir
            {workspace_root}/{task_id}/        ← 挂载到容器 /workspace

        容器内路径结构：
            /workspace/repo/                   ← 容器内仓库根

        例如：
            /workspaces/task-001/repo/src/main.py
              → /workspace/repo/src/main.py

        :param host_path: 宿主机上的绝对路径
        :return: 容器内的对应绝对路径
        :raises SandboxError: 路径不在沙箱工作区内
        """
        host_path = Path(host_path).resolve()
        mount_src = self.host_work_dir.parent  # 例如 /workspaces/task-001
        try:
            relative = host_path.relative_to(mount_src)
        except ValueError:
            raise SandboxError(
                f"路径 '{host_path}' 不在沙箱工作区 '{mount_src}' 内，"
                "拒绝映射到容器路径。"
            )
        container_path = "/workspace" / relative
        return str(container_path).replace("\\", "/")

    def path_to_host(self, container_path: str) -> Path:
        """将容器内路径映射回宿主机路径（path_to_container 的反向操作）。

        例如：
            /workspace/repo/src/main.py
              → /workspaces/task-001/repo/src/main.py

        :param container_path: 容器内的绝对路径
        :return: 宿主机的对应绝对路径
        :raises SandboxError: 路径不在容器 /workspace 内
        """
        container_path = Path(container_path.replace("\\", "/"))
        if not str(container_path).startswith("/workspace"):
            raise SandboxError(
                f"容器路径 '{container_path}' 不在 /workspace 内，"
                "拒绝映射到宿主机路径。"
            )
        relative = str(container_path).replace("/workspace", "", 1).lstrip("/")
        # 注意：如果 relative 是 "repo/src/main.py"，实际宿主机路径应该是
        # host_work_dir.parent / relative = workspace_root/task_id/repo/src/main.py
        mount_src = self.host_work_dir.parent  # 例如 /workspaces/task-001
        host_path = (mount_src / relative).resolve()
        return host_path

    def affected_files(self) -> list[str]:
        """获取沙箱工作区内被修改的文件列表（相对于仓库根目录）。

        通过对 host_work_dir 执行 git diff --name-only 实现。
        同时包括未跟踪的新文件。

        :return: 修改文件的相对路径列表，例如 ["src/main.py", "tests/test_foo.py"]
        """
        if not self.host_work_dir.exists():
            return []
        try:
            # 获取已修改和已暂存的文件
            result_staged = subprocess.run(
                ["git", "diff", "--name-only", "--staged"],
                capture_output=True, text=True,
                cwd=str(self.host_work_dir),
                timeout=30,
            )
            result_unstaged = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True, text=True,
                cwd=str(self.host_work_dir),
                timeout=30,
            )
            # 获取未跟踪文件
            result_untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                capture_output=True, text=True,
                cwd=str(self.host_work_dir),
                timeout=30,
            )
            files = set()
            for result in (result_staged, result_unstaged, result_untracked):
                if result.returncode == 0 and result.stdout.strip():
                    for line in result.stdout.strip().splitlines():
                        line = line.strip()
                        if line:
                            files.add(line)
            return sorted(files)
        except Exception:
            return []

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        # 注意：不自动清理，以便外部检查生成的文件和 diff

