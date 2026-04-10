from langchain_core.tools import tool

@tool
def read_file(file_path: str) -> str:
    """读取指定路径的代码文件内容"""
    # 这里交由第二组实现真实的文件读取
    return f"Mock content of {file_path}"

@tool
def bash_terminal(command: str) -> str:
    """在终端中执行 bash 命令，比如运行 pytest"""
    # 交由第二组实现真实终端
    return f"Mock execution of: {command}\nTests passed."

@tool
def patch_file(file_path: str, diff_content: str) -> str:
    """根据 diff 修改文件内容"""
    return f"Successfully patched {file_path}"

# 供主链调用的工具列表
AGENT_TOOLS = [read_file, bash_terminal, patch_file]