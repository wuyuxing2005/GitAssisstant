"""多层降级上下文压缩器

按代价从低到高排列，越靠后越贵；只有上一层无法把 token 压到预算内时才触发下一层。
当前已实现 Tool Result Budget、History Snip 和兜底的 AutoCompact，其余层级保留为后续扩展点。

层级表（从轻到重）：
1. Tool Result Budget   — 工具结果上下文留预览                      [已实现]
2. History Snip         — 移除明显冗余消息（HISTORY_SNIP gate）       [已实现]
3. Microcompact         — 本地清理旧工具结果，不调 API              [TODO]//好像没必要？Claude到底如何实现缓存的
4. Context Collapse     — 只读折叠视图，不改原始数据                [TODO]//同上
5. AutoCompact          — fork 子 Agent 调 LLM 生成结构化摘要        [已实现]

边界安全（始终运行）：保证不会在 AIMessage(tool_calls) 与对应 ToolMessage 之间切断，
否则 OpenAI 接口会以 "Messages with role 'tool' must be a response to a preceding
message with 'tool_calls'" 拒绝请求。
"""

from __future__ import annotations

import json
import os

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


DEFAULT_MAX_CONTEXT_TOKENS = 128000
DEFAULT_KEEP_RECENT_MESSAGES = 6
DEFAULT_SUMMARY_MAX_TOKENS = 8000
DEFAULT_TOOL_OUTPUT_TRUNCATE = 300
DEFAULT_TOOL_OUTPUT_TRUNCATE_FOR_PROMPT = 400
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}

CHARS_PER_TOKEN_CJK = 2
CHARS_PER_TOKEN_EN = 4


class ContextCompressor:
    """多层降级压缩器。轻量层优先，必要时再进入 AutoCompact 兜底。"""

    def __init__(
        self,
        compactor_llm=None,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        keep_recent_messages: int = DEFAULT_KEEP_RECENT_MESSAGES,
        summary_max_tokens: int = DEFAULT_SUMMARY_MAX_TOKENS,
        tool_output_truncate: int = DEFAULT_TOOL_OUTPUT_TRUNCATE,
        history_snip_enabled: bool | None = None,
    ):
        self.compactor_llm = compactor_llm
        self.max_context_tokens = max_context_tokens
        self.keep_recent_messages = keep_recent_messages
        self.summary_max_tokens = summary_max_tokens
        self.tool_output_truncate = tool_output_truncate
        self.history_snip_enabled = (
            self._env_enabled("HISTORY_SNIP")
            if history_snip_enabled is None
            else history_snip_enabled
        )
        self.last_stats: dict[str, int | bool] = {}
        # 给 orchestrator._node_react 算 compression_stats 用，保持字段存在即可。
        self.level0_window = keep_recent_messages
        self.level1_window = 0

    # ============================================================
    # 主入口
    # ============================================================

    async def compress(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """超出预算才触发多级压缩；否则只做边界清理后原样返回。"""
        if not messages:
            return []
        self._reset_stats(messages)

        # TODO: 在这里继续插入 Microcompact / Context Collapse
        # 每一层尝试把 estimate_tokens 压到 max_context_tokens 以下，压到了就 return。

        if self.estimate_tokens(messages) <= self.max_context_tokens:
            self.last_stats["after_compress_tokens"] = self.estimate_tokens(messages)
            return self._drop_orphan_tool_messages(list(messages))

        tool_budgeted = self._apply_tool_result_budget(messages)
        self._record_tool_budget(messages, tool_budgeted)
        if self.estimate_tokens(tool_budgeted) <= self.max_context_tokens:
            self.last_stats["after_compress_tokens"] = self.estimate_tokens(tool_budgeted)
            return self._drop_orphan_tool_messages(tool_budgeted)

        snipped = self.snip_compact_if_needed(tool_budgeted)
        if self.estimate_tokens(snipped) <= self.max_context_tokens:
            self.last_stats["after_compress_tokens"] = self.estimate_tokens(snipped)
            return self._drop_orphan_tool_messages(snipped)

        compacted = await self._autocompact(snipped)
        self.last_stats["after_compress_tokens"] = self.estimate_tokens(compacted)
        return compacted

    def compress_sync(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """同步入口：不调用 LLM，仅做机械裁剪。供测试或异步上下文外的调用使用。"""
        if not messages:
            return []
        self._reset_stats(messages)
        if self.estimate_tokens(messages) <= self.max_context_tokens:
            self.last_stats["after_compress_tokens"] = self.estimate_tokens(messages)
            return self._drop_orphan_tool_messages(list(messages))
        tool_budgeted = self._apply_tool_result_budget(messages)
        self._record_tool_budget(messages, tool_budgeted)
        if self.estimate_tokens(tool_budgeted) <= self.max_context_tokens:
            self.last_stats["after_compress_tokens"] = self.estimate_tokens(tool_budgeted)
            return self._drop_orphan_tool_messages(tool_budgeted)
        snipped = self.snip_compact_if_needed(tool_budgeted)
        if self.estimate_tokens(snipped) <= self.max_context_tokens:
            self.last_stats["after_compress_tokens"] = self.estimate_tokens(snipped)
            return self._drop_orphan_tool_messages(snipped)
        compacted = self._mechanical_fallback(snipped)
        self.last_stats["after_compress_tokens"] = self.estimate_tokens(compacted)
        return compacted

    # ============================================================
    # Level 1: Tool Result Budget
    # ============================================================

    def _apply_tool_result_budget(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """Level 1：总上下文超限时，把工具结果替换为短预览。"""
        result: list[BaseMessage] = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                result.append(self._truncate_tool_message(msg))
            else:
                result.append(msg)
        return result

    # ============================================================
    # Level 2: History Snip
    # ============================================================

    def snip_compact_if_needed(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """Feature-gated 历史剪裁层：删除历史区中可判定的冗余消息。"""
        if not self.history_snip_enabled:
            return list(messages)

        before_tokens = self.estimate_tokens(messages)
        if before_tokens <= self.max_context_tokens:
            return list(messages)

        snipped, removed_messages = self._snip_history(messages)
        after_tokens = self.estimate_tokens(snipped)
        self.last_stats["snip_tokens_freed"] = max(0, before_tokens - after_tokens)
        self.last_stats["snip_removed_messages"] = removed_messages
        self.last_stats["after_snip_tokens"] = after_tokens
        return snipped

    def _snip_history(self, messages: list[BaseMessage]) -> tuple[list[BaseMessage], int]:
        cut = self._safe_cut_point(messages)
        if cut <= 0:
            return list(messages), 0

        groups = self._message_groups(messages[:cut])
        kept_recent = list(messages[cut:])
        seen_signatures: set[str] = set()
        kept_groups_reversed: list[list[BaseMessage]] = []
        removed_messages = 0

        for group in reversed(groups):
            signature = self._snip_signature(group)
            if signature and signature in seen_signatures:
                removed_messages += len(group)
                continue
            if signature:
                seen_signatures.add(signature)

            compacted_group = [self._snip_message_content(msg) for msg in group]
            if len(compacted_group) == 1 and self._is_empty_assistant(compacted_group[0]):
                removed_messages += 1
                continue
            kept_groups_reversed.append(compacted_group)

        result: list[BaseMessage] = []
        for group in reversed(kept_groups_reversed):
            result.extend(group)
        result.extend(kept_recent)
        return self._drop_orphan_tool_messages(result), removed_messages

    def _message_groups(self, messages: list[BaseMessage]) -> list[list[BaseMessage]]:
        groups: list[list[BaseMessage]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            tool_calls = getattr(msg, "tool_calls", []) or []
            if isinstance(msg, AIMessage) and tool_calls:
                call_ids = {
                    call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
                    for call in tool_calls
                }
                group = [msg]
                i += 1
                while i < len(messages) and isinstance(messages[i], ToolMessage):
                    call_id = getattr(messages[i], "tool_call_id", "")
                    if call_id and call_ids and call_id not in call_ids:
                        break
                    group.append(messages[i])
                    i += 1
                groups.append(group)
                continue
            groups.append([msg])
            i += 1
        return groups

    def _snip_signature(self, group: list[BaseMessage]) -> str:
        if not group:
            return ""
        first = group[0]
        if isinstance(first, (HumanMessage, SystemMessage)):
            return ""
        tool_calls = getattr(first, "tool_calls", []) or []
        if isinstance(first, AIMessage) and tool_calls:
            normalized_calls = []
            for call in tool_calls:
                if isinstance(call, dict):
                    normalized_calls.append({
                        "name": call.get("name", ""),
                        "args": call.get("args", {}) or {},
                    })
                else:
                    normalized_calls.append({
                        "name": getattr(call, "name", ""),
                        "args": getattr(call, "args", {}) or {},
                    })
            tool_results = [
                self._normalize_for_snip(getattr(msg, "content", "") or "")
                for msg in group[1:]
                if isinstance(msg, ToolMessage)
            ]
            payload = {"calls": normalized_calls, "results": tool_results}
            return f"tool_calls:{json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)}"
        if isinstance(first, AIMessage):
            text = self._normalize_for_snip(self._get_message_text(first))
            return f"ai:{text}" if text else ""
        return ""

    def _snip_message_content(self, msg: BaseMessage) -> BaseMessage:
        tool_calls = getattr(msg, "tool_calls", []) or []
        if isinstance(msg, AIMessage) and tool_calls and (getattr(msg, "content", "") or "").strip():
            return AIMessage(content="", tool_calls=tool_calls)
        return msg

    def _is_empty_assistant(self, msg: BaseMessage) -> bool:
        return (
            isinstance(msg, AIMessage)
            and not (getattr(msg, "content", "") or "").strip()
            and not (getattr(msg, "tool_calls", []) or [])
        )

    def _normalize_for_snip(self, text: str) -> str:
        return " ".join((text or "").strip().split())

    # ============================================================
    # AutoCompact（Level 5）
    # ============================================================

    async def _autocompact(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        cut = self._safe_cut_point(messages)
        if cut <= 0:
            # 全部消息都在"近期窗口"里，没法再压；退回机械裁剪。
            return self._mechanical_fallback(messages)

        if self.compactor_llm is None:
            # 没配压缩模型 → 不调 LLM，退回机械裁剪。
            return self._mechanical_fallback(messages)

        to_summarize = messages[:cut]
        kept = messages[cut:]

        try:
            summary_text = await self._llm_summarize(to_summarize)
        except Exception as exc:
            print(f"⚠️ AutoCompact LLM 调用失败，降级为机械裁剪: {exc}")
            return self._mechanical_fallback(messages)

        if not summary_text:
            return self._mechanical_fallback(messages)

        summary_msg = HumanMessage(content=f"[历史上下文摘要]\n{summary_text}")
        return self._drop_orphan_tool_messages([summary_msg] + kept)

    def _safe_cut_point(self, messages: list[BaseMessage]) -> int:
        """决定从哪条开始保留原文：默认保留最近 keep_recent_messages 条，
        然后把切点向前回退，避免落在 ToolMessage 上（会和上面的 AIMessage(tool_calls) 拆开）。
        """
        target = max(0, len(messages) - self.keep_recent_messages)
        while 0 < target < len(messages) and isinstance(messages[target], ToolMessage):
            target -= 1
        return target

    async def _llm_summarize(self, messages: list[BaseMessage]) -> str:
        prompt = self._build_summary_prompt(messages)
        response = await self.compactor_llm.ainvoke(prompt)
        return (getattr(response, "content", "") or "").strip()

    def _build_summary_prompt(self, messages: list[BaseMessage]) -> str:
        formatted = self._format_messages_for_prompt(messages)
        return (
            "你正在帮一个代码修复 Agent 压缩对话上下文。把下面这段对话历史浓缩成"
            f"结构化的「长期记忆」，不超过 {self.summary_max_tokens} tokens。\n\n"
            "需要保留的信息：\n"
            "1. 已确认的事实（仓库结构、关键文件、错误根因、读到的关键代码片段）\n"
            "2. 已尝试过的方案及结果（失败也要保留，写明原因，避免后续重蹈覆辙）\n"
            "3. 还在猜测、未验证的假设\n"
            "4. 修改过的文件 / 测试结果 / commit hash 等关键产物\n\n"
            "输出格式（严格四段，每段一行一项，不要输出其他内容）：\n"
            "## 已确认事实\n- ...\n"
            "## 已尝试的方案\n- 方案 → 成功/失败（原因）\n"
            "## 当前假设 / 未验证\n- ...\n"
            "## 关键产物\n- ...\n\n"
            "对话历史：\n"
            f"{formatted}"
        )

    def _format_messages_for_prompt(self, messages: list[BaseMessage]) -> str:
        lines = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                continue
            if isinstance(msg, HumanMessage):
                content = self._truncate(msg.content or "", 400)
                lines.append(f"[用户] {content}")
            elif isinstance(msg, AIMessage):
                content = self._truncate((msg.content or "").strip(), 300)
                lines.append(f"[Agent] {content}" if content else "[Agent] (仅工具调用)")
                for call in getattr(msg, "tool_calls", []) or []:
                    name = call.get("name", "?") if isinstance(call, dict) else getattr(call, "name", "?")
                    args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
                    lines.append(f"  └ 调用 {name}({self._brief_args(args)})")
            elif isinstance(msg, ToolMessage):
                content = self._truncate(msg.content or "", DEFAULT_TOOL_OUTPUT_TRUNCATE_FOR_PROMPT)
                name = getattr(msg, "name", None) or "tool"
                lines.append(f"[工具 {name}] {content}")
        return "\n".join(lines)

    # ============================================================
    # 机械降级（LLM 不可用 / 不值得调用时的兜底的兜底）
    # ============================================================

    def _mechanical_fallback(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """无 LLM 时的最后手段：截断老工具输出 + 缩短 AI 文本，不调 API。"""
        cutoff = max(0, len(messages) - self.keep_recent_messages)
        # 边界回退，跟 _safe_cut_point 同逻辑
        while 0 < cutoff < len(messages) and isinstance(messages[cutoff], ToolMessage):
            cutoff -= 1

        result: list[BaseMessage] = []
        for i, msg in enumerate(messages):
            if i >= cutoff:
                result.append(msg)
                continue
            if isinstance(msg, ToolMessage):
                result.append(self._truncate_tool_message(msg))
            elif isinstance(msg, AIMessage):
                result.append(self._compress_ai_message(msg))
            else:
                result.append(msg)
        return self._drop_orphan_tool_messages(result)

    # ============================================================
    # 工具方法
    # ============================================================

    def _env_enabled(self, name: str) -> bool:
        return os.getenv(name, "").strip().lower() in TRUTHY_ENV_VALUES

    def _reset_stats(self, messages: list[BaseMessage]) -> None:
        before_tokens = self.estimate_tokens(messages)
        self.last_stats = {
            "history_snip_enabled": self.history_snip_enabled,
            "before_tokens": before_tokens,
            "after_tool_budget_tokens": before_tokens,
            "tool_budget_tokens_freed": 0,
            "snip_tokens_freed": 0,
            "snip_removed_messages": 0,
            "after_snip_tokens": before_tokens,
            "after_compress_tokens": before_tokens,
        }

    def _record_tool_budget(
        self,
        before_messages: list[BaseMessage],
        after_messages: list[BaseMessage],
    ) -> None:
        before_tokens = self.estimate_tokens(before_messages)
        after_tokens = self.estimate_tokens(after_messages)
        self.last_stats["after_tool_budget_tokens"] = after_tokens
        self.last_stats["tool_budget_tokens_freed"] = max(0, before_tokens - after_tokens)

    def estimate_tokens(self, messages: list[BaseMessage]) -> int:
        total = 0
        for msg in messages:
            content = self._get_message_text(msg)
            total += self._estimate_text_tokens(content) + 4
        return total

    def _estimate_text_tokens(self, text: str) -> int:
        if not text:
            return 0
        cjk_chars = sum(1 for c in text if '一' <= c <= '鿿')
        other_chars = len(text) - cjk_chars
        return cjk_chars // CHARS_PER_TOKEN_CJK + other_chars // CHARS_PER_TOKEN_EN

    def _get_message_text(self, msg: BaseMessage) -> str:
        content = getattr(msg, "content", "") or ""
        tool_calls = getattr(msg, "tool_calls", []) or []
        if tool_calls:
            content += json.dumps(tool_calls, ensure_ascii=False, default=str)
        return content

    def _truncate_tool_message(self, msg: ToolMessage) -> ToolMessage:
        content = getattr(msg, "content", "") or ""
        if len(content) <= self.tool_output_truncate:
            return msg
        truncated = content[: self.tool_output_truncate] + f"\n...[已截断，原始长度 {len(content)}]"
        return ToolMessage(
            content=truncated,
            tool_call_id=getattr(msg, "tool_call_id", ""),
            name=getattr(msg, "name", None),
        )

    def _compress_ai_message(self, msg: AIMessage) -> AIMessage:
        content = (getattr(msg, "content", "") or "").strip()
        tool_calls = getattr(msg, "tool_calls", []) or []
        if len(content) > 200:
            content = content[:200] + "..."
        return AIMessage(content=content, tool_calls=tool_calls)

    def _drop_orphan_tool_messages(
        self, messages: list[BaseMessage]
    ) -> list[BaseMessage]:
        seen_call_ids: set[str] = set()
        result: list[BaseMessage] = []
        for msg in messages:
            if isinstance(msg, AIMessage):
                for call in getattr(msg, "tool_calls", []) or []:
                    call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
                    if call_id:
                        seen_call_ids.add(call_id)
                result.append(msg)
            elif isinstance(msg, ToolMessage):
                call_id = getattr(msg, "tool_call_id", "")
                if call_id and call_id in seen_call_ids:
                    result.append(msg)
            else:
                result.append(msg)
        return result

    def _brief_args(self, args) -> str:
        if not isinstance(args, dict) or not args:
            return ""
        parts = []
        for key, value in list(args.items())[:2]:
            val_str = str(value)
            if len(val_str) > 40:
                val_str = val_str[:40] + "..."
            parts.append(f"{key}={val_str}")
        return ", ".join(parts)

    def _truncate(self, text: str, limit: int) -> str:
        text = text.strip().replace("\n", " ")
        if len(text) <= limit:
            return text
        return text[:limit] + "..."
