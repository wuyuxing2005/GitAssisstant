"""
Trace 数据加载器

负责 Agent Trace 数据的持久化存储和加载。
"""

import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime
import threading

from app.models.trace import AgentTrace
from app.core.config import get_settings

settings = get_settings()


class TraceLoader:
    """
    Trace 数据加载器

    使用 JSON 文件存储 Trace 数据，支持按任务 ID 索引。
    存储路径：{data_dir}/traces/{task_id}/{sample_id}.json
    """

    def __init__(self):
        self._traces_cache: dict[str, dict[str, AgentTrace]] = {}
        self._lock = threading.Lock()
        self._initialize_storage()

    def _initialize_storage(self):
        """初始化存储目录"""
        traces_dir = Path(settings.data_dir) / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        self.traces_root_dir = traces_dir

    def _get_trace_dir(self, task_id: str) -> Path:
        """获取指定任务的 Trace 存储目录"""
        trace_dir = self.traces_root_dir / task_id
        trace_dir.mkdir(exist_ok=True)
        return trace_dir

    def _get_trace_file(self, task_id: str, sample_id: str) -> Path:
        """获取指定 Trace 的文件路径"""
        trace_dir = self._get_trace_dir(task_id)
        return trace_dir / f"{sample_id}.json"

    def _load_traces_to_cache(self, task_id: str):
        """将指定任务的所有 Trace 加载到缓存中"""
        if task_id in self._traces_cache:
            return

        with self._lock:
            if task_id in self._traces_cache:
                return

            self._traces_cache[task_id] = {}
            trace_dir = self._get_trace_dir(task_id)

            if trace_dir.exists():
                for trace_file in trace_dir.glob("*.json"):
                    try:
                        with open(trace_file, 'r', encoding='utf-8') as f:
                            trace_data = json.load(f)
                            trace = AgentTrace(**trace_data)
                            self._traces_cache[task_id][trace.sample_id] = trace
                    except (json.JSONDecodeError, Exception) as e:
                        print(f"警告：加载执行链路文件失败 {trace_file}: {e}")

    def save_trace(self, trace: AgentTrace) -> None:
        """
        保存单条 Trace 数据到文件和缓存

        Args:
            trace: AgentTrace 对象
        """
        task_id = trace.task_id
        sample_id = trace.sample_id

        with self._lock:
            # 确保任务缓存存在
            if task_id not in self._traces_cache:
                self._traces_cache[task_id] = {}

            # 保存到内存缓存
            self._traces_cache[task_id][sample_id] = trace

        # 保存到文件
        trace_file = self._get_trace_file(task_id, sample_id)
        try:
            with open(trace_file, 'w', encoding='utf-8') as f:
                json.dump(trace.model_dump(), f, indent=2, default=str)
        except Exception as e:
            raise IOError(f"保存执行链路到 {trace_file} 失败：{e}")

    def get_trace(self, task_id: str, sample_id: str) -> Optional[AgentTrace]:
        """
        获取单条 Trace 数据

        Args:
            task_id: 任务 ID
            sample_id: 样本 ID

        Returns:
            AgentTrace 对象，不存在则返回 None
        """
        self._load_traces_to_cache(task_id)

        with self._lock:
            if task_id not in self._traces_cache:
                return None
            return self._traces_cache[task_id].get(sample_id)

    def get_traces_by_task(self, task_id: str) -> list[AgentTrace]:
        """
        获取指定任务的所有 Trace 数据

        Args:
            task_id: 任务 ID

        Returns:
            AgentTrace 列表
        """
        self._load_traces_to_cache(task_id)

        with self._lock:
            if task_id not in self._traces_cache:
                return []
            return list(self._traces_cache[task_id].values())

    def get_traces_by_ids(self, task_id: str, sample_ids: list[str]) -> list[AgentTrace]:
        """
        获取指定样本的 Trace 数据

        Args:
            task_id: 任务 ID
            sample_ids: 样本 ID 列表

        Returns:
            AgentTrace 列表
        """
        self._load_traces_to_cache(task_id)
        traces = []

        with self._lock:
            if task_id not in self._traces_cache:
                return []

            for sample_id in sample_ids:
                if sample_id in self._traces_cache[task_id]:
                    traces.append(self._traces_cache[task_id][sample_id])

        return traces

    def delete_trace(self, task_id: str, sample_id: str) -> bool:
        """
        删除单条 Trace 数据

        Args:
            task_id: 任务 ID
            sample_id: 样本 ID

        Returns:
            是否成功删除
        """
        self._load_traces_to_cache(task_id)

        with self._lock:
            if task_id not in self._traces_cache:
                return False
            if sample_id not in self._traces_cache[task_id]:
                return False

            # 从缓存中移除
            del self._traces_cache[task_id][sample_id]

        # 删除文件
        trace_file = self._get_trace_file(task_id, sample_id)
        if trace_file.exists():
            try:
                trace_file.unlink()
                return True
            except Exception:
                return False
        return True

    def delete_traces(self, task_id: str) -> bool:
        """
        删除指定任务的所有 Trace 数据

        Args:
            task_id: 任务 ID

        Returns:
            是否成功删除
        """
        with self._lock:
            # 从缓存中移除
            if task_id in self._traces_cache:
                del self._traces_cache[task_id]

        # 删除目录和所有文件
        trace_dir = self._get_trace_dir(task_id)
        if trace_dir.exists():
            try:
                import shutil
                shutil.rmtree(trace_dir)
                return True
            except Exception:
                return False
        return True

    def count_traces(self, task_id: str) -> int:
        """
        统计指定任务的 Trace 数量

        Args:
            task_id: 任务 ID

        Returns:
            Trace 数量
        """
        self._load_traces_to_cache(task_id)

        with self._lock:
            if task_id not in self._traces_cache:
                return 0
            return len(self._traces_cache[task_id])


# 单例实例
trace_loader = TraceLoader()
