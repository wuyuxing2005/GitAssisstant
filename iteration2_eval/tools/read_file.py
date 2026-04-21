"""
文件读取工具
"""

import os
from pathlib import Path


def execute(file_path: str) -> str:
    """
    读取文件内容，返回带行号的文本
    """
    
    # 参数检查
    if not file_path:
        return "Error: file_path is required"
    
    path = Path(file_path)
    
    # 文件存在性检查
    if not path.exists():
        return f"Error: File not found - {file_path}"
    
    if not path.is_file():
        return f"Error: Not a file - {file_path}"
    
    # 读取文件
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # 尝试 GBK 编码（Windows 中文环境）
        try:
            with open(path, 'r', encoding='gbk') as f:
                content = f.read()
        except Exception as e:
            return f"Error: Cannot decode file - {str(e)}"
    except PermissionError:
        return f"Error: Permission denied - {file_path}"
    except Exception as e:
        return f"Error: {str(e)}"
    
    # 添加行号
    lines = content.split('\n')
    numbered_lines = [f"{i+1:4d}|{line}" for i, line in enumerate(lines)]
    
    return '\n'.join(numbered_lines)

