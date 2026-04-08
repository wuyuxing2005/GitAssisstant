from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class ActionRequest:
    """定义向第二组(工具链)发起的动作请求"""
    tool_name: str
    tool_input: Dict[str, Any]
    thought: str  # 执行此动作前的思考过程

@dataclass
class ActionResponse:
    """第二组返回的执行结果"""
    observation: str
    success: bool
    error_message: Optional[str] = None

def execute_tool():
    pass

def get_tools_description():
    pass