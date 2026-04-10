import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from .orchestrator import AgentOrchestrator
class SessionManager:
    def __init__(self, orchestrator):
        # 引用全局唯一的引擎
        self.orchestrator:AgentOrchestrator = orchestrator
        # 核心：维护 仓库路径 -> thread_id 的映射
        self.sessions: Dict[str, str] = {} 
        self.current_repo: Optional[str] = None

    def create_or_switch_session(self, repo_path: str):
        """创建或切换到一个仓库会话"""
        if repo_path not in self.sessions:
            # 如果是新仓库，分配一个新的 thread_id
            self.sessions[repo_path] = f"thread_{repo_path}"
        
        # 切换当前指针
        self.current_repo = repo_path
        return self.sessions[repo_path]

    def set_issue(self, issue_desc: str):
        """为当前仓库注入初始 Issue 并初始化状态"""
        if not self.current_repo:
            raise ValueError("请先使用 /repo 指定仓库")
        
        thread_id = self.sessions[self.current_repo]
        config = {"configurable": {"thread_id": thread_id}}
        
        # 定义该仓库的初始状态 (AgentState)
        initial_state = {
            "repo_path": self.current_repo,
            "issue_description": issue_desc,
            "status": "INIT",
            "iteration_count": 0,
            "max_iterations": 15,
            "plan": [],
            "messages": [], # LangGraph 会自动处理追加
            "trajectory": [],
            "reflexion_notes": ""
        }
        
        # 将初始状态强行写入 LangGraph 的内存中
        self.orchestrator.graph.update_state(config, initial_state)

    def get_current_thread_id(self) -> str:
        """获取当前正在操作的 thread_id"""
        if not self.current_repo:
            raise ValueError("当前没有激活的仓库，请使用 /repo <path>")
        return self.sessions[self.current_repo]

    def get_current_state(self) -> dict:
        """获取当前仓库的实时状态数据"""
        thread_id = self.get_current_thread_id()
        config = {"configurable": {"thread_id": thread_id}}
        
        # 从 Orchestrator 的 MemorySaver 中读取对应的存档
        state_snapshot = self.orchestrator.graph.get_state(config)
        
        # 如果还没初始化过，返回空字典
        return state_snapshot.values if state_snapshot else {}