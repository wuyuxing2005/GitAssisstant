# sandbox_manager.py
"""
沙箱生命周期管理器 — 管理所有会话的 DockerSandbox 实例。

职责：
  - 按 thread_id 创建、查找、停止和清理 DockerSandbox
  - 确保同一会话复用同一个沙箱实例
  - 程序退出时批量清理所有沙箱容器
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from ..sandbox import DockerSandbox


class SandboxManager:
    """管理所有会话的 DockerSandbox 实例。

    使用方式：
        manager = SandboxManager()

        # 为某个会话获取或创建沙箱
        sandbox = manager.get_or_create(thread_id="thread_abc", repo_path="/path/to/repo")

        # 后续同一 thread_id 返回同一个实例
        same_sandbox = manager.get(thread_id="thread_abc")

        # 会话结束时清理
        manager.stop("thread_abc")
        manager.cleanup("thread_abc")

        # 程序退出时清理所有
        manager.stop_all()
    """

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        progress_callback: Callable[[dict], None] | None = None,
    ):
        """
        :param workspace_root: 沙箱工作区根目录，默认为当前目录下的 workspaces/
        """
        self.workspace_root = (Path(workspace_root) if workspace_root else Path.cwd()).resolve()
        # thread_id → DockerSandbox
        self._sandboxes: Dict[str, DockerSandbox] = {}
        self.progress_callback = progress_callback

    def set_progress_callback(self, progress_callback: Callable[[dict], None] | None) -> None:
        self.progress_callback = progress_callback

    def get_or_create(self, thread_id: str, repo_path: str) -> DockerSandbox:
        """根据 thread_id 获取已有沙箱，不存在则创建并启动新的。

        创建时会：
          1. 实例化 DockerSandbox
          2. 加载仓库的 .agent-sandbox.yml 配置
          3. 拉取镜像、创建容器、挂载工作目录
          4. 执行 install 命令
          5. 将沙箱实例缓存到内部字典

        :param thread_id: 会话的 thread_id（作为 task_id 使用）
        :param repo_path: 宿主机上的仓库路径
        :return: 已启动的 DockerSandbox 实例
        """
        if thread_id in self._sandboxes:
            return self._sandboxes[thread_id]

        sandbox = DockerSandbox(
            task_id=thread_id,
            repo_path=Path(repo_path),
            workspace_root=self.workspace_root,
            progress_callback=self.progress_callback,
        )
        sandbox.start()
        self._sandboxes[thread_id] = sandbox
        return sandbox

    def get(self, thread_id: str) -> Optional[DockerSandbox]:
        """获取已有的沙箱实例。不存在时返回 None 而非创建。"""
        return self._sandboxes.get(thread_id)

    def stop(self, thread_id: str) -> None:
        """停止并删除指定会话的沙箱容器（工作目录保留）。"""
        sandbox = self._sandboxes.pop(thread_id, None)
        if sandbox is not None:
            sandbox.stop()

    def stop_all(self) -> None:
        """停止所有已管理的沙箱容器。通常在程序退出时调用。"""
        for thread_id in list(self._sandboxes.keys()):
            self.stop(thread_id)

    def cleanup(self, thread_id: str) -> None:
        """清理指定会话的宿主机工作目录（在 stop 之后调用，带重试兼容 Windows）。"""
        sandbox = self._sandboxes.get(thread_id)
        if sandbox is not None:
            sandbox.cleanup()
        else:
            # 即使缓存中没有，也尝试从已知路径清理
            host_work_dir = self.workspace_root / thread_id / "repo"
            import shutil
            import time
            if not host_work_dir.exists():
                return
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    shutil.rmtree(host_work_dir)
                    return
                except PermissionError:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                    # 最后一次重试仍失败则静默跳过，避免阻塞任务删除流程

