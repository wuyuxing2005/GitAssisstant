from __future__ import annotations

import json
import re
from typing import Any

from ...core.utils.git import extract_modified_files_from_diff, is_temporary_file


async def get_commit_plan_from_agent(
    llm: Any,
    issue_description: str,
    diff: str,
) -> dict | None:
    """Ask the LLM which changed files should be committed."""
    modified_files = extract_modified_files_from_diff(diff)

    prompt = f"""你是 Git 提交助手。根据以下信息，决定应该提交哪些文件以及撰写 commit message。

## 当前任务（Issue）
{issue_description}

## 修改的文件列表
{chr(10).join(f'- {f}' for f in modified_files)}

## 完整的修改内容（diff）
{diff[:6000]}

## 请按照以下 JSON 格式输出（不要输出其他内容）
```json
{{
    "files": ["file1.py", "file2.py"],
    "message": "fix: 简要描述修复内容"
}}
```
## 规则
只提交与当前任务和用户追加要求直接相关的文件。

新增的源码文件和测试文件如果属于本次需求，也必须列入 files 数组。

commit message 使用中文，格式：fix: 简要描述本次完整变更

如果修改了多个文件，全部列入 files 数组

不要添加 pycache、pytest_cache 等临时文件"""
    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        json_match = re.search(r"json\s*(\{.*?\})\s*", content, re.DOTALL)
        if json_match:
            plan = json.loads(json_match.group(1))
        else:
            plan = json.loads(content)
        if "files" not in plan or "message" not in plan:
            print(f"❌ Agent 输出的提交方案格式不正确:{plan}")
            return None

        allowed_files = set(modified_files)
        plan["files"] = [
            file_path
            for file_path in plan.get("files", [])
            if file_path in allowed_files and not is_temporary_file(file_path)
        ]
        if not plan["files"]:
            plan["files"] = [
                file_path
                for file_path in modified_files
                if not is_temporary_file(file_path)
            ]
        return plan
    except Exception as exc:
        print(f"❌ 解析 Agent 提交方案失败: {exc}")
        return None

