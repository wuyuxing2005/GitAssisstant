"""
目录列表工具
"""

import os
from pathlib import Path


def execute(directory: str = ".", show_hidden: bool = False) -> str:
    """
    列出目录中的文件和子目录
    """
    
    # 参数检查
    if not directory:
        directory = "."
    
    path = Path(directory)
    
    # 目录存在性检查
    if not path.exists():
        return f"Error: Directory not found - {directory}"
    
    if not path.is_dir():
        return f"Error: Not a directory - {directory}"
    
    # 列出内容
    try:
        items = []
        for item in path.iterdir():
            # 跳过隐藏文件（除非指定显示）
            if not show_hidden and item.name.startswith('.'):
                continue
            
            # 标记类型
            item_type = "[DIR] " if item.is_dir() else "[FILE]"
            
            # 获取大小（仅文件）
            size_str = ""
            if item.is_file():
                try:
                    size = item.stat().st_size
                    if size < 1024:
                        size_str = f" ({size} B)"
                    elif size < 1024 * 1024:
                        size_str = f" ({size / 1024:.1f} KB)"
                    else:
                        size_str = f" ({size / (1024 * 1024):.1f} MB)"
                except:
                    pass
            
            items.append(f"{item_type} {item.name}{size_str}")
        
        # 排序（目录在前，文件在后）
        items.sort(key=lambda x: (not x.startswith("[DIR]"), x.lower()))
        
        if not items:
            return f"Directory is empty: {directory}"
        
        # 构建返回结果
        result = f"Contents of {path.absolute()}:\n"
        result += f"Total: {len(items)} items\n"
        result += "-" * 50 + "\n"
        result += '\n'.join(items)
        
        return result
        
    except PermissionError:
        return f"Error: Permission denied - {directory}"
    except Exception as e:
        return f"Error: {str(e)}"

