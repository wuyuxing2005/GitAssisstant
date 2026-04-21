"""
Pytest 测试运行工具
"""

import subprocess
import os
import re


def execute(test_path: str = "tests/", options: str = "-v", timeout: int = 60) -> str:
    """
    运行 pytest 测试，返回格式化的测试结果
    """
    
    # 参数检查
    if not test_path:
        test_path = "tests/"
    
    # 构建命令
    command = f"pytest {test_path} {options}"
    
    # 执行测试
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd()
        )
        
        output = result.stdout + result.stderr
        
        # 解析测试结果
        parsed = _parse_pytest_output(output, result.returncode, test_path)
        
        return parsed
        
    except subprocess.TimeoutExpired:
        return f"Error: Tests timed out after {timeout} seconds"
    except FileNotFoundError:
        return "Error: pytest not found. Please install pytest: pip install pytest"
    except Exception as e:
        return f"Error: {str(e)}"


def _parse_pytest_output(output: str, returncode: int, test_path: str) -> str:
    """
    解析 pytest 输出，提取关键信息
    """
    
    # 提取测试统计
    passed = 0
    failed = 0
    skipped = 0
    error = 0
    
    # 匹配各种可能的统计格式
    passed_match = re.search(r'(\d+) passed', output)
    failed_match = re.search(r'(\d+) failed', output)
    skipped_match = re.search(r'(\d+) skipped', output)
    error_match = re.search(r'(\d+) error', output)
    
    if passed_match:
        passed = int(passed_match.group(1))
    if failed_match:
        failed = int(failed_match.group(1))
    if skipped_match:
        skipped = int(skipped_match.group(1))
    if error_match:
        error = int(error_match.group(1))
    
    # 如果没解析到任何统计，可能 pytest 没有运行测试
    if passed == 0 and failed == 0 and skipped == 0 and error == 0:
        if "no tests ran" in output.lower():
            return f"No tests found in {test_path}"
        elif "ERROR:" in output:
            return f"Pytest error: {output[:500]}"
        else:
            return output[:500] + ("..." if len(output) > 500 else "")
    
    # 构建结果
    result_parts = []
    
    # 状态标识
    if returncode == 0:
        result_parts.append(f"✓ 所有测试通过 ({passed} passed)")
    else:
        result_parts.append(f"✗ 测试失败: {passed} passed, {failed} failed")
        if skipped > 0:
            result_parts[-1] += f", {skipped} skipped"
        if error > 0:
            result_parts[-1] += f", {error} errors"
    
    # 提取失败的测试详情
    if failed > 0 or error > 0:
        failures = _extract_failures(output)
        
        if failures:
            result_parts.append(f"\n失败详情:")
            for i, failure in enumerate(failures[:5], 1):
                result_parts.append(f"  {i}. {failure['test']}")
                result_parts.append(f"     {failure['error']}")
            
            if len(failures) > 5:
                result_parts.append(f"  ... 还有 {len(failures) - 5} 个失败")
    
    # 如果有测试总结，添加进去
    summary_match = re.search(r'=+ (.*?) =+', output)
    if summary_match and "in" in summary_match.group(1):
        result_parts.append(f"\n{summary_match.group(0)}")
    
    return '\n'.join(result_parts)


def _extract_failures(output: str) -> list:
    """
    从 pytest 输出中提取失败测试的详细信息
    """
    failures = []
    lines = output.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 查找失败测试的开始
        if 'FAILED' in line or 'ERROR' in line and '____' in line:
            failure = {'test': '', 'error': ''}
            
            # 提取测试名称
            test_match = re.search(r'_{3,} (.*?) _{3,}', line)
            if test_match:
                failure['test'] = test_match.group(1)
            
            # 查找错误信息（接下来的几行）
            i += 1
            error_lines = []
            while i < len(lines):
                next_line = lines[i]
                if next_line.startswith('____') or next_line.startswith('===='):
                    break
                if next_line.strip():
                    error_lines.append(next_line.strip())
                i += 1
            
            # 提取关键错误信息
            for err_line in error_lines:
                if 'AssertionError' in err_line or 'Error' in err_line:
                    failure['error'] = err_line[:100]
                    break
                elif '>' in err_line and 'E' in err_line:
                    failure['error'] = err_line[:100]
                    break
            
            if not failure['error'] and error_lines:
                failure['error'] = error_lines[0][:100]
            
            if failure['test'] or failure['error']:
                failures.append(failure)
        else:
            i += 1
    
    return failures
