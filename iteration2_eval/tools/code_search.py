"""
代码搜索工具
"""

import os
from pathlib import Path


def execute(pattern: str, directory: str = ".") -> str:
    """
    在指定目录中搜索包含匹配模式的代码行
    """
    
    # 参数检查
    if not pattern:
        return "Error: pattern is required"
    
    if not directory:
        directory = "."
    
    path = Path(directory)
    
    # 目录存在性检查
    if not path.exists():
        return f"Error: Directory not found - {directory}"
    
    if not path.is_dir():
        return f"Error: Not a directory - {directory}"
    
    # 要搜索的文件扩展名
    code_extensions = {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php"}
    
    results = []
    
    try:
        # 遍历目录
        for root, dirs, files in os.walk(path):
            # 跳过隐藏目录和虚拟环境
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["__pycache__", "node_modules", "venv", ".git"]]
            
            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()
                
                # 只搜索代码文件
                if ext not in code_extensions:
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        
                    for line_num, line in enumerate(lines, start=1):
                        if pattern in line:
                            # 相对路径显示
                            rel_path = file_path.relative_to(path)
                            results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                            
                except UnicodeDecodeError:
                    # 尝试 GBK 编码
                    try:
                        with open(file_path, 'r', encoding='gbk') as f:
                            lines = f.readlines()
                            
                        for line_num, line in enumerate(lines, start=1):
                            if pattern in line:
                                rel_path = file_path.relative_to(path)
                                results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                    except:
                        pass
                except:
                    pass
                    
    except Exception as e:
        return f"Error: {str(e)}"
    
    # 返回结果
    if not results:
        return f"No matches found for '{pattern}' in {directory}"
    
    # 限制结果数量
    max_results = 50
    if len(results) > max_results:
        results = results[:max_results]
        results.append(f"\n... and {len(results) - max_results} more matches (truncated)")
    
    return '\n'.join(results)

