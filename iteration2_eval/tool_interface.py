from dataclasses import dataclass, field
from typing import TypedDict,List, Dict, Any, Optional

@dataclass
class ActionRequest:
    """工具请求"""
    tool_name: str
    tool_input: Dict[str, Any]
    thought: str  # 执行此动作前的思考过程

@dataclass
class ActionResponse:
    """工具返回结果"""
    observation: str
    success: bool
    error_message: Optional[str] = None

class ToolDef(TypedDict):
    name: str
    description: str
    input_schema: Dict[str, Any]

tool_definitions: List[ToolDef] = [
    {
        "name": "read_file",
        "description": "Read the contents of a file. Returns the file content with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to read"
                }
            },
            "required": ["file_path"]
        }
    },...
]
async def execute_tool(name: str, inp: dict) -> str:
    handlers = {
        "read_file": _read_file,
        "write_file": _write_file,
        "edit_file": _edit_file,
        "list_files": _list_files,
        "grep_search": _grep_search,
        "run_shell": _run_shell,
    }
    handler = handlers.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    return _truncate_result(handler(inp))


def get_tools_description():
    pass
