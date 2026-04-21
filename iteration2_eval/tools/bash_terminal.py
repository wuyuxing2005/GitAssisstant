"""
Bash终端执行工具
"""

import subprocess
import os


# 危险命令黑名单
DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "dd if=",
    "mkfs",
    "format",
    ":(){ :|:& };:",  # fork bomb
    "> /dev/sda",
    "chmod -R 777 /",
    "chown -R",
]


def execute(command: str, timeout: int = 30) -> str:
    """
    执行 bash 命令，返回执行结果
    """
    
    # 参数检查
    if not command:
        return "Error: command is required"
    
    # 安全检查
    for pattern in DANGEROUS_PATTERNS:
        if pattern in command.lower():
            return f"Error: Dangerous command detected - '{pattern}' is not allowed"
    
    # 执行命令
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd()  # 在当前工作目录执行
        )
        
        # 合并 stdout 和 stderr
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        
        if not output:
            output = "(no output)"
        
        # 添加返回码信息
        if result.returncode != 0:
            output = f"[Exit code: {result.returncode}]\n{output}"
        
        return output
        
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error: {str(e)}"

