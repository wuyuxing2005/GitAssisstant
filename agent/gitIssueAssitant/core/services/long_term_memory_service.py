from __future__ import annotations

import json
import re
from pathlib import Path

from dotenv import load_dotenv

from gitIssueAssitant.core.repositories.long_term_memory_repository import (
    long_term_memory_repository,
)
from gitIssueAssitant.core.schemas.memory import LongTermMemoryRecord
from gitIssueAssitant.core.schemas.task import TaskRecord, TimelineEntry
from gitIssueAssitant.core.agent.agent import LLM_factory
from gitIssueAssitant.core.services.task_service import task_service
from gitIssueAssitant.core.utils.time import now_local


MAX_MEMORY_CONTENT_CHARS = 1400
MAX_PROMPT_MEMORY_CHARS = 3500
MAX_LLM_SOURCE_CHARS = 9000
TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_./-]{2,}|[\u4e00-\u9fff]{2,}")
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _compact(text: str, limit: int = 500) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def _repo_key(repo_source: str) -> str:
    raw = repo_source.strip().replace("\\", "/").rstrip("/")
    if raw.endswith(".git"):
        raw = raw[:-4]
    parts = [part for part in raw.split("/") if part]
    if len(parts) >= 2 and ("github.com" in raw or ":" in raw):
        return "/".join(parts[-2:]).lower()
    if len(parts) >= 2:
        return "/".join(parts[-2:]).lower()
    return (parts[-1] if parts else raw).lower()


def _keywords(*parts: str) -> set[str]:
    words: set[str] = set()
    for part in parts:
        for match in TOKEN_PATTERN.findall(part or ""):
            word = match.strip().lower()
            if len(word) >= 2:
                words.add(word)
    return words


def _extract_json_object(text: str) -> dict | None:
    raw = (text or "").strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1).strip()
    else:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            raw = match.group(0)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


class LongTermMemoryService:
    def list_memories(self, limit: int = 50) -> list[LongTermMemoryRecord]:
        return long_term_memory_repository.list(limit)

    def delete_memory(self, memory_id: str) -> bool:
        return long_term_memory_repository.delete(memory_id)

    def clear_memories(self) -> int:
        return long_term_memory_repository.clear()

    def _selected_entries(self, task: TaskRecord) -> list[TimelineEntry]:
        result = task.result
        if result is None:
            return []
        important_types = {"plan", "reflection", "assistant"}
        selected = [
            entry
            for entry in result.timeline
            if entry.event_type in important_types and entry.content.strip()
        ]
        tool_entries = [
            entry
            for entry in result.timeline
            if entry.event_type == "tool"
            and any(name in entry.title for name in ("run_pytest", "git_diff", "git_status"))
            and entry.content.strip()
        ]
        return selected[-4:] + tool_entries[-2:]

    def build_from_task(self, task: TaskRecord) -> LongTermMemoryRecord | None:
        if task.status not in {"completed", "failed"}:
            return None
        result = task.result
        if result is None:
            return None

        lines = [
            f"任务: {task.name}",
            f"仓库: {task.config.repo_source}",
            f"结果: {task.status}",
            f"Issue: {_compact(task.config.issue_input, 360)}",
        ]
        if task.description.strip():
            lines.append(f"补充说明: {_compact(task.description, 260)}")
        if result.summary.strip():
            lines.append(f"结果摘要: {_compact(result.summary, 320)}")
        if result.current_state and result.current_state.selected_skill:
            lines.append(f"使用 Skill: {result.current_state.selected_skill}")

        edit_count = next((metric.value for metric in result.metrics if metric.name == "file_edit_count"), 0)
        test_count = next((metric.value for metric in result.metrics if metric.name == "test_run_count"), 0)
        lines.append(f"过程指标: 修改工具 {int(edit_count)} 次，测试 {int(test_count)} 次")

        if result.fix_report and result.fix_report.suggested_pr_title:
            lines.append(f"推荐提交: {result.fix_report.suggested_pr_title}")

        entries = self._selected_entries(task)
        if entries:
            lines.append("可复用经验:")
            for entry in entries:
                lines.append(f"- {entry.title}: {_compact(entry.content, 260)}")

        content = "\n".join(lines).strip()
        if not content:
            return None
        if len(content) > MAX_MEMORY_CONTENT_CHARS:
            content = f"{content[:MAX_MEMORY_CONTENT_CHARS].rstrip()}..."

        now = now_local()
        tags = sorted(
            list(_keywords(task.name, task.config.issue_input, task.description))[:12]
        )
        repo_tag = _repo_key(task.config.repo_source)
        if repo_tag:
            tags.insert(0, repo_tag)

        return LongTermMemoryRecord(
            id=f"mem-{task.id}",
            task_id=task.id,
            task_name=task.name,
            repo_source=task.config.repo_source,
            issue_input=task.config.issue_input,
            outcome=task.status,
            content=content,
            tags=tags,
            source="rule",
            created_at=now,
            updated_at=now,
        )

    def _llm_source(self, task: TaskRecord) -> str:
        result = task.result
        if result is None:
            return ""

        metric_lines = [
            f"- {metric.name}: {metric.value}{f' {metric.unit}' if metric.unit else ''}"
            for metric in result.metrics
        ]
        timeline_lines = []
        for entry in result.timeline[-16:]:
            content = _compact(entry.content, 700)
            tool_calls = ", ".join(tool_call.name for tool_call in entry.tool_calls[:5])
            if tool_calls:
                timeline_lines.append(
                    f"[{entry.node}/{entry.event_type}] {entry.title} | tools={tool_calls}\n{content}"
                )
            else:
                timeline_lines.append(f"[{entry.node}/{entry.event_type}] {entry.title}\n{content}")

        report = ""
        if result.fix_report and result.fix_report.markdown:
            report = _compact(result.fix_report.markdown, 1600)

        source = "\n\n".join(
            [
                f"任务名称: {task.name}",
                f"仓库: {task.config.repo_source}",
                f"状态: {task.status}",
                f"Issue:\n{task.config.issue_input}",
                f"用户补充说明:\n{task.description or '无'}",
                f"结果摘要:\n{result.summary or '无'}",
                f"指标:\n" + ("\n".join(metric_lines) or "无"),
                f"修复报告:\n{report or '无'}",
                "最近执行轨迹:\n" + ("\n\n".join(timeline_lines) or "无"),
            ]
        )
        if len(source) > MAX_LLM_SOURCE_CHARS:
            return f"{source[:MAX_LLM_SOURCE_CHARS].rstrip()}..."
        return source

    async def build_from_task_with_llm(self, task: TaskRecord, llm) -> LongTermMemoryRecord | None:
        fallback = self.build_from_task(task)
        if fallback is None:
            return None
        if llm is None:
            return fallback

        source = self._llm_source(task)
        prompt = (
            "你是代码修复 Agent 的长期记忆整理器。请根据一次任务执行记录，"
            "提炼对未来同仓库或相似问题真正有帮助的经验。\n\n"
            "要求：\n"
            "- 不要复述流水账，保留可复用的定位路径、根因、有效修复策略、验证方法、踩坑和禁忌。\n"
            "- 如果任务失败，也总结失败原因、阻塞点、下次优先检查什么。\n"
            "- 不要编造执行记录中没有的事实。\n"
            "- 输出中文，简洁但信息密度高。\n"
            "- 严格输出 JSON，不要 Markdown 代码块之外的解释。\n\n"
            "JSON 格式：\n"
            "{\n"
            '  "content": "长期记忆正文，使用 4-8 条短要点，最多 900 字",\n'
            '  "tags": ["仓库或模块", "问题类型", "工具或测试", "其他关键词"]\n'
            "}\n\n"
            f"任务记录：\n{source}"
        )

        try:
            response = await llm.ainvoke(prompt)
            payload = _extract_json_object(str(getattr(response, "content", "")))
        except Exception:
            return fallback

        if not payload:
            return fallback
        content = str(payload.get("content") or "").strip()
        if not content:
            return fallback
        if len(content) > MAX_MEMORY_CONTENT_CHARS:
            content = f"{content[:MAX_MEMORY_CONTENT_CHARS].rstrip()}..."

        raw_tags = payload.get("tags") or []
        tags = [
            str(tag).strip().lower()
            for tag in raw_tags
            if str(tag).strip()
        ][:12] if isinstance(raw_tags, list) else []
        merged_tags = []
        for tag in [*fallback.tags, *tags]:
            if tag and tag not in merged_tags:
                merged_tags.append(tag)

        return fallback.model_copy(
            update={
                "content": content,
                "tags": merged_tags[:16],
                "source": "llm",
                "updated_at": now_local(),
            }
        )

    def remember_task(self, task: TaskRecord) -> LongTermMemoryRecord | None:
        memory = self.build_from_task(task)
        if memory is None:
            return None
        return long_term_memory_repository.save(memory)

    async def remember_task_with_llm(self, task: TaskRecord, llm) -> LongTermMemoryRecord | None:
        memory = await self.build_from_task_with_llm(task, llm)
        if memory is None:
            return None
        return long_term_memory_repository.save(memory)

    def has_memory_for_task(self, task_id: str) -> bool:
        return long_term_memory_repository.get_by_task_id(task_id) is not None

    def _load_llm_for_rebuild(self):
        try:
            load_dotenv(WORKSPACE_ROOT / ".env", override=False)
            return LLM_factory()
        except Exception:
            return None

    async def rebuild_from_recent_tasks(self, limit: int = 20) -> tuple[list[LongTermMemoryRecord], int]:
        memories: list[LongTermMemoryRecord] = []
        skipped_count = 0
        llm = self._load_llm_for_rebuild()
        for task in task_service.list_task_records()[:limit]:
            if self.has_memory_for_task(task.id):
                skipped_count += 1
                continue
            memory = await self.remember_task_with_llm(task, llm)
            if memory is not None:
                memories.append(memory)
        return memories, skipped_count

    def relevant_memories(
        self,
        *,
        repo_source: str,
        issue_input: str,
        description: str = "",
        limit: int = 5,
    ) -> list[LongTermMemoryRecord]:
        repo = _repo_key(repo_source)
        query_words = _keywords(repo_source, issue_input, description)

        scored: list[tuple[int, LongTermMemoryRecord]] = []
        for memory in long_term_memory_repository.list(80):
            score = 0
            if repo and _repo_key(memory.repo_source) == repo:
                score += 8
            memory_words = set(memory.tags) | _keywords(memory.issue_input, memory.content)
            score += len(query_words & memory_words)
            if memory.outcome == "completed":
                score += 1
            if score > 0:
                scored.append((score, memory))

        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [memory for _, memory in scored[:limit]]

    def build_prompt_context(
        self,
        *,
        repo_source: str,
        issue_input: str,
        description: str = "",
        limit: int = 5,
    ) -> str:
        memories = self.relevant_memories(
            repo_source=repo_source,
            issue_input=issue_input,
            description=description,
            limit=limit,
        )
        if not memories:
            return ""

        lines = [
            "以下是最近任务沉淀的长期记忆，仅作为排查线索和历史经验参考；",
            "如果与当前仓库实际代码或工具结果冲突，必须以当前证据为准。",
        ]
        for index, memory in enumerate(memories, start=1):
            lines.append(
                f"\n[{index}] {memory.task_name} ({memory.outcome}, {memory.updated_at:%Y-%m-%d %H:%M})"
            )
            lines.append(memory.content)

        text = "\n".join(lines).strip()
        if len(text) > MAX_PROMPT_MEMORY_CHARS:
            text = f"{text[:MAX_PROMPT_MEMORY_CHARS].rstrip()}..."
        return text


long_term_memory_service = LongTermMemoryService()
