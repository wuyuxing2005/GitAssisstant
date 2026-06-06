from __future__ import annotations

import os
from pathlib import Path

from .git import extract_modified_files_from_diff


def extract_test_summary_from_state(state: dict) -> tuple[str, str]:
    messages = state.get("messages") or []
    for message in reversed(messages):
        if getattr(message, "name", None) == "run_pytest":
            return "run_pytest", str(getattr(message, "content", "") or "无输出")
    return "未检测到测试命令", "未检测到测试输出"


def latest_agent_text_from_state(state: dict) -> str:
    for item in reversed(state.get("trajectory", []) or []):
        if item.get("type") in {"ai", "reflection"} and str(item.get("content", "")).strip():
            return str(item.get("content", "")).strip()
    return ""


def build_fix_report_markdown_from_context(
    *,
    report_title: str,
    issue_description: str,
    diff: str,
    root_cause: str = "",
    test_command: str = "未检测到测试命令",
    test_output: str = "未检测到测试输出",
    commit_plan: dict | None = None,
) -> tuple[str, str, str]:
    modified_files = extract_modified_files_from_diff(diff)
    root_cause = root_cause or "Agent 未输出明确根因；请结合 diff 和测试结果复核。"
    pr_title = (commit_plan or {}).get("message") or "fix: agent 修复"
    pr_body = (
        "## Summary\n"
        f"- {issue_description.splitlines()[0] if issue_description else 'Agent 修复'}\n\n"
        "## Test\n"
        f"- {test_command}\n"
    )
    key_changes = "\n".join(
        f"- {file_path}: 根据 diff 完成针对性修改。"
        for file_path in modified_files
    ) or "- 未检测到文件修改。"
    markdown = "\n".join(
        [
            f"# {report_title}",
            "",
            "## Issue 摘要",
            issue_description or "未提供 Issue 描述。",
            "",
            "## 根因分析",
            root_cause,
            "",
            "## 修改文件列表",
            "\n".join(f"- {file_path}" for file_path in modified_files) or "- 无",
            "",
            "## 关键修改说明",
            key_changes,
            "",
            "## 测试命令和测试结果",
            f"命令: `{test_command}`",
            "",
            "```text",
            test_output[:4000],
            "```",
            "",
            "## 剩余风险",
            "- 建议人工复核边界条件、异常输入和未覆盖路径。",
            "",
            "## 建议的 PR 标题",
            pr_title,
            "",
            "## 建议的 PR 描述",
            pr_body,
            "",
        ]
    )
    return markdown, pr_title, pr_body


def build_fix_report_markdown(
    state: dict,
    issue_description: str,
    diff: str,
    commit_plan: dict | None,
) -> tuple[str, str, str]:
    test_command, test_output = extract_test_summary_from_state(state)
    return build_fix_report_markdown_from_context(
        report_title="Agent 修复报告",
        issue_description=issue_description,
        diff=diff,
        root_cause=latest_agent_text_from_state(state),
        test_command=test_command,
        test_output=test_output,
        commit_plan=commit_plan,
    )


def write_fix_report(markdown: str, session_id: str | None) -> Path:
    home = Path(os.getenv("GIT_ISSUE_ASSISTANT_HOME") or Path.cwd()).resolve()
    reports_dir = home / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_name = f"{session_id or 'session'}-fix-report.md"
    report_path = reports_dir / report_name
    report_path.write_text(markdown, encoding="utf-8")
    return report_path

