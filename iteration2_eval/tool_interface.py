from dataclasses import dataclass, field
from typing import TypedDict,List, Dict, Any, Optional
from tools.read_file import execute as read_file_execute
from tools.bash_terminal import execute as bash_execute
from tools.code_search import execute as code_search_execute
from tools.patch_file import execute as patch_execute
from tools.pytest_runner import execute as pytest_execute
from tools.write_file import execute as write_file_execute
from tools.list_files import execute as list_files_execute

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
        "run_test": _run_test,
    }
    handler = handlers.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    return _truncate_result(handler(inp))


def get_tools_description():
    pass

def _read_file(inp: dict) -> str:
    """文件读取工具适配器"""
    file_path = inp.get("file_path", "")
    return read_file_execute(file_path)

def _run_shell(inp: dict) -> str:
    """终端执行适配器"""
    command = inp.get("command", "")
    return bash_execute(command)

def _grep_search(inp: dict) -> str:
    """代码搜索适配器"""
    pattern = inp.get("pattern", "")
    directory = inp.get("directory", ".")
    return code_search_execute(pattern, directory)

def _edit_file(inp: dict) -> str:
    """代码修改适配器"""
    file_path = inp.get("file_path", "")
    diff = inp.get("diff", "")
    return patch_execute(file_path, diff)

def _run_test(inp: dict) -> str:
    """测试运行适配器"""
    test_path = inp.get("test_path", "tests/")
    options = inp.get("options", "-v")
    return pytest_execute(test_path, options)

def _write_file(inp: dict) -> str:
    """文件写入适配器"""
    file_path = inp.get("file_path", "")
    content = inp.get("content", "")
    return write_file_execute(file_path, content)

def _list_files(inp: dict) -> str:
    """目录列表适配器"""
    directory = inp.get("directory", ".")
    return list_files_execute(directory)