# agent_state.py
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class AgentState:
    """全局 Agent 状态，贯穿整个生命周期"""
    issue_description: str
    repo_path: str
    
    # --- 推理与规划 ---
    plan: List[str] = field(default_factory=list)
    current_step_index: int = 0
    reflexion_notes: str = ""  # 反思记录（失败后总结的经验）
    
    # --- 历史轨迹 (ReAct Memory) ---
    trajectory: List[Dict[str, Any]] = field(default_factory=list) 
    
    # --- 状态控制 ---
    iteration_count: int = 0
    max_iterations: int = 15
    status: str = "INIT"  # 可选: INIT, PLANNING, RUNNING, REFLECTING, SUCCESS, FAILED
    
    # --- 结果 ---
    final_patch: str = ""
    
    def add_trajectory(self, thought: str, action: str, action_input: dict, observation: str):
        """供主链记录完整交互轨迹，也是第三组进行可视化展示的数据源"""
        self.trajectory.append({
            "iteration": self.iteration_count,
            "thought": thought,
            "action": action,
            "action_input": action_input,
            "observation": observation
        })