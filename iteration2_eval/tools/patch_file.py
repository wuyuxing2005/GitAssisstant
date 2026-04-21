"""
代码修改工具 - 应用 diff patch
"""

import os
from pathlib import Path


def execute(file_path: str, diff: str) -> str:
    """
    根据 unified diff 格式的补丁修改文件
    """
    
    # 参数检查
    if not file_path:
        return "Error: file_path is required"
    
    if not diff:
        return "Error: diff is required"
    
    path = Path(file_path)
    
    # 文件存在性检查
    if not path.exists():
        return f"Error: File not found - {file_path}"
    
    if not path.is_file():
        return f"Error: Not a file - {file_path}"
    
    # 读取原文件
    try:
        with open(path, 'r', encoding='utf-8') as f:
            original_content = f.read()
            original_lines = original_content.splitlines(keepends=True)
    except UnicodeDecodeError:
        try:
            with open(path, 'r', encoding='gbk') as f:
                original_content = f.read()
                original_lines = original_content.splitlines(keepends=True)
        except Exception as e:
            return f"Error: Cannot read file - {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"
    
    # 解析并应用 diff
    try:
        patched_lines = _apply_patch(original_lines, diff)
    except ValueError as e:
        return f"Error: Invalid diff format - {str(e)}"
    except Exception as e:
        return f"Error: Failed to apply patch - {str(e)}"
    
    # 备份原文件
    backup_path = path.with_suffix(path.suffix + ".bak")
    try:
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.writelines(original_lines)
    except:
        pass
    
    # 写入修改后的内容
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(patched_lines)
    except Exception as e:
        return f"Error: Cannot write file - {str(e)}"
    
    return f"Successfully patched {file_path}\nBackup saved to {backup_path}"


def _apply_patch(original_lines: list, diff: str) -> list:
    """
    应用 unified diff 格式的补丁（简化版）
    """
    diff_lines = diff.strip().splitlines()
    
    # 找到第一个 @@ 行
    hunk_start = 0
    for i, line in enumerate(diff_lines):
        if line.startswith('@@'):
            hunk_start = i
            break
    else:
        raise ValueError("No hunk header found")
    
    # 解析 hunk 头: @@ -old_start,old_count +new_start,new_count @@
    header = diff_lines[hunk_start]
    parts = header.split()
    old_info = parts[1].lstrip('-').split(',')
    old_start = int(old_info[0]) - 1  # 转为0-based索引
    
    # 提取 hunk 内容（跳过 @@ 行）
    hunk_lines = diff_lines[hunk_start + 1:]
    
    # 应用修改
    result = []
    orig_idx = 0
    hunk_idx = 0
    
    # 添加 hunk 之前的行
    while orig_idx < old_start and orig_idx < len(original_lines):
        result.append(original_lines[orig_idx])
        orig_idx += 1
    
    # 处理 hunk
    while hunk_idx < len(hunk_lines):
        line = hunk_lines[hunk_idx]
        
        if line.startswith(' '):  # 上下文行
            if orig_idx < len(original_lines):
                result.append(original_lines[orig_idx])
            orig_idx += 1
            hunk_idx += 1
        elif line.startswith('-'):  # 删除行
            orig_idx += 1
            hunk_idx += 1
        elif line.startswith('+'):  # 添加行
            result.append(line[1:] + '\n')
            hunk_idx += 1
        else:
            hunk_idx += 1
    
    # 添加剩余的行
    while orig_idx < len(original_lines):
        result.append(original_lines[orig_idx])
        orig_idx += 1
    
    return result

