"""
文件写入工具
"""

from pathlib import Path
import os


def execute(file_path: str, content: str) -> str:
    """
    写入文件内容（创建新文件或覆盖已有文件）
    """
    
    # 参数检查
    if not file_path:
        return "Error: file_path is required"
    
    if content is None:
        return "Error: content is required"
    
    path = Path(file_path)
    
    # 安全检查：防止写入到工作区外
    try:
        full_path = path.resolve()
        cwd = Path.cwd().resolve()
        if not str(full_path).startswith(str(cwd)):
            return f"Error: Cannot write outside current workspace"
    except:
        pass
    
    # 备份原文件（如果存在）
    backup_path = None
    if path.exists():
        if path.is_dir():
            return f"Error: Path is a directory - {file_path}"
        try:
            backup_path = path.with_suffix(path.suffix + ".bak")
            with open(path, 'r', encoding='utf-8') as f:
                original = f.read()
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original)
        except:
            pass
    
    # 写入文件
    try:
        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        if backup_path:
            return f"Successfully wrote to {file_path}\nBackup saved to {backup_path}"
        else:
            return f"Successfully created {file_path}"
        
    except PermissionError:
        return f"Error: Permission denied - {file_path}"
    except Exception as e:
        return f"Error: {str(e)}"

