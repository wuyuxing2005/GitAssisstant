"""多级上下文压缩器

将对话历史按时间远近分为三个压缩级别：
- Level 0 (近期): 保留原始消息，不做压缩
- Level 1 (中期): 压缩工具输出，保留 AI 推理和关键结论
- Level 2 (远期): 将多条消息合并为一条摘要
"""

from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)


# 默认窗口大小
DEFAULT_LEVEL0_WINDOW = 6   # 最近 6 条消息保持原样
DEFAULT_LEVEL1_WINDOW = 12  # 再往前 12 条做中度压缩
# 更早的消息做高度压缩（合并为摘要）

# 工具输出截断阈值
TOOL_OUTPUT_TRUNCATE = 300
LEVEL2_SUMMARY_MAX_ITEMS = 8

# 粗略估算：1 token ≈ 2 中文字符 或 4 英文字符
CHARS_PER_TOKEN_CJK = 2
CHARS_PER_TOKEN_EN = 4


class ContextCompressor:
    """多级上下文压缩器，在发送给 LLM 前压缩历史消息。"""

    def __init__(
        self,
        level0_window: int = DEFAULT_LEVEL0_WINDOW,
        level1_window: int = DEFAULT_LEVEL1_WINDOW,
        tool_output_truncate: int = TOOL_OUTPUT_TRUNCATE,
        max_context_tokens: int = 0,
    ):
        self.level0_window = level0_window
        self.level1_window = level1_window
        self.tool_output_truncate = tool_output_truncate
        self.max_context_tokens = max_context_tokens

    def estimate_tokens(self, messages: list[BaseMessage]) -> int:
        """估算消息列表的 token 数（无需 tiktoken 依赖）。

        使用字符级启发式：中文按 2 字符/token，英文按 4 字符/token，
        加上每条消息固定 4 token 的格式开销。
        """
        total = 0
        for msg in messages:
            content = self._get_message_text(msg)
            total += self._estimate_text_tokens(content) + 4
        return total

    def compress(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """对消息列表执行多级压缩，返回压缩后的消息列表。

        如果设置了 max_context_tokens，会自适应调整压缩窗口直到满足预算。
        """
        if len(messages) <= self.level0_window:
            return list(messages)

        result = self._compress_with_windows(
            messages, self.level0_window, self.level1_window
        )

        if self.max_context_tokens > 0:
            result = self._adaptive_compress(messages, result)

        return result

    def _adaptive_compress(
        self, original: list[BaseMessage], current: list[BaseMessage]
    ) -> list[BaseMessage]:
        """如果压缩后仍超预算，逐步收紧窗口。"""
        estimated = self.estimate_tokens(current)
        if estimated <= self.max_context_tokens:
            return current

        # 逐步缩小 level0 和 level1 窗口
        l0 = self.level0_window
        l1 = self.level1_window

        for _ in range(3):
            l1 = max(2, l1 // 2)
            result = self._compress_with_windows(original, l0, l1)
            if self.estimate_tokens(result) <= self.max_context_tokens:
                return result

            l0 = max(2, l0 // 2)
            result = self._compress_with_windows(original, l0, l1)
            if self.estimate_tokens(result) <= self.max_context_tokens:
                return result

        return result

    def _compress_with_windows(
        self, messages: list[BaseMessage], l0: int, l1: int
    ) -> list[BaseMessage]:
        """使用指定窗口大小执行压缩。"""
        level0_start = max(0, len(messages) - l0)
        level1_start = max(0, level0_start - l1)

        level2_msgs = messages[:level1_start]
        level1_msgs = messages[level1_start:level0_start]
        level0_msgs = messages[level0_start:]

        compressed = []

        if level2_msgs:
            summary = self._compress_level2(level2_msgs)
            compressed.append(summary)

        if level1_msgs:
            compressed.extend(self._compress_level1(level1_msgs))

        compressed.extend(level0_msgs)
        return compressed

    def _estimate_text_tokens(self, text: str) -> int:
        """根据字符类型混合估算 token 数。"""
        if not text:
            return 0
        cjk_chars = sum(1 for c in text if '一' <= c <= '鿿')
        other_chars = len(text) - cjk_chars
        return cjk_chars // CHARS_PER_TOKEN_CJK + other_chars // CHARS_PER_TOKEN_EN

    def _get_message_text(self, msg: BaseMessage) -> str:
        """提取消息的全部文本内容（包括 tool_calls 的序列化）。"""
        content = getattr(msg, "content", "") or ""
        tool_calls = getattr(msg, "tool_calls", []) or []
        if tool_calls:
            import json
            content += json.dumps(tool_calls, ensure_ascii=False)
        return content

    def _compress_level1(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """中度压缩：截断工具输出，保留 AI 消息的核心内容。"""
        result = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                result.append(self._truncate_tool_message(msg))
            elif isinstance(msg, AIMessage):
                result.append(self._compress_ai_message(msg))
            else:
                result.append(msg)
        return result

    def _compress_level2(self, messages: list[BaseMessage]) -> HumanMessage:
        """高度压缩：将多条消息合并为一条摘要消息。"""
        actions = []
        findings = []

        for msg in messages:
            if isinstance(msg, AIMessage):
                tool_calls = getattr(msg, "tool_calls", []) or []
                if tool_calls:
                    for call in tool_calls[:2]:
                        name = call.get("name", "unknown")
                        args = call.get("args", {})
                        brief_args = self._brief_args(args)
                        actions.append(f"{name}({brief_args})")
                else:
                    content = (getattr(msg, "content", "") or "").strip()
                    if content:
                        findings.append(self._truncate(content, 80))

            elif isinstance(msg, ToolMessage):
                content = (getattr(msg, "content", "") or "").strip()
                name = getattr(msg, "name", "") or "tool"
                if content and not content.lower().startswith("error:"):
                    findings.append(f"[{name}] {self._truncate(content, 60)}")
                elif content.lower().startswith("error:"):
                    findings.append(f"[{name}] 错误: {self._truncate(content[6:], 60)}")

            elif isinstance(msg, HumanMessage):
                content = (getattr(msg, "content", "") or "").strip()
                if content and not content.startswith("["):
                    findings.append(f"[指令] {self._truncate(content, 60)}")

        summary_parts = []
        if actions:
            unique_actions = list(dict.fromkeys(actions))[:LEVEL2_SUMMARY_MAX_ITEMS]
            summary_parts.append("已执行操作: " + ", ".join(unique_actions))
        if findings:
            unique_findings = list(dict.fromkeys(findings))[:LEVEL2_SUMMARY_MAX_ITEMS]
            summary_parts.append("关键发现:\n" + "\n".join(f"- {f}" for f in unique_findings))

        summary_text = (
            "[历史上下文摘要]\n" + "\n".join(summary_parts)
            if summary_parts
            else "[历史上下文摘要] 早期对话已压缩，无关键信息。"
        )

        return HumanMessage(content=summary_text)

    def _truncate_tool_message(self, msg: ToolMessage) -> ToolMessage:
        """截断过长的工具输出。"""
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
        """压缩 AI 消息：保留 tool_calls，截断过长的文本内容。"""
        content = (getattr(msg, "content", "") or "").strip()
        tool_calls = getattr(msg, "tool_calls", []) or []

        if len(content) > 200:
            content = content[:200] + "..."

        return AIMessage(
            content=content,
            tool_calls=tool_calls,
        )

    def _brief_args(self, args: dict) -> str:
        """将工具参数压缩为简短描述。"""
        if not args:
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
