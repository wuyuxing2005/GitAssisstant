from __future__ import annotations

import json
import os
import re

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from .tools.tools import AGENT_TOOLS


def _get_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _validate_llm_settings(model_name: str, base_url: str | None) -> None:
    if base_url and not re.match(r"^https?://", base_url):
        raise RuntimeError(
            "OPENAI_BASE_URL 配置无效，必须是 http:// 或 https:// 开头的接口地址，"
            "不能把 API Key 填到 OPENAI_BASE_URL。"
        )

    if model_name == "hunyuan-lite" and not base_url:
        raise RuntimeError(
            "MODEL_NAME=hunyuan-lite 但未配置 OPENAI_BASE_URL。"
            "如果你使用 OpenAI 官方接口，请把 MODEL_NAME 改成可用的 OpenAI 模型；"
            "如果你使用兼容网关，请补全 OPENAI_BASE_URL。"
        )


class Agent:
    def __init__(self, llm: ChatOpenAI, tools=AGENT_TOOLS):
        self.llm = llm
        self.tools = list(tools)
        self._llm_with_tools_cache = {}
        self.llm_with_tools = self._llm_for_tools()
        self.last_token_usage: dict[str, int] = {}

    def set_tools(self, tools: list) -> None:
        """Set the base tools this agent may expose to the model."""
        self.tools = list(tools)
        self._llm_with_tools_cache = {}
        self.llm_with_tools = self._llm_for_tools()

    def _tool_name(self, tool) -> str:
        return str(getattr(tool, "name", "") or getattr(tool, "__name__", ""))

    def _tools_for_allowed(self, allowed_tools: list[str] | None = None) -> list:
        if not allowed_tools:
            return self.tools
        allowed = {name.strip() for name in allowed_tools if str(name).strip()}
        return [tool for tool in self.tools if self._tool_name(tool) in allowed]

    def _llm_for_tools(self, allowed_tools: list[str] | None = None):
        selected_tools = self._tools_for_allowed(allowed_tools)
        cache_key = tuple(self._tool_name(tool) for tool in selected_tools)
        if cache_key not in self._llm_with_tools_cache:
            self._llm_with_tools_cache[cache_key] = self.llm.bind_tools(selected_tools)
        return self._llm_with_tools_cache[cache_key]

    def _extract_usage(self, response) -> dict[str, int]:
        """从 LLM 响应中提取 token 用量并缓存到 last_token_usage。"""
        metadata = getattr(response, "response_metadata", None) or {}
        usage = metadata.get("token_usage", {})
        self.last_token_usage = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
        return self.last_token_usage

    # ========== 分层规划 ==========

    def _build_skill_and_plan_prompt(
        self,
        issue_description: str,
        skills_catalog: str,
    ) -> str:
        return (
            "你负责 Skill 路由和是修复规划。\n\n"
            "可用 Skill：\n"
            f"{skills_catalog}\n\n"
            "请根据 Issue 选择最匹配的 Skill。如果都不合适或都不能显著优于通用流程，"
            "选 \"none\"，按通用 bug 修复处理。\n\n"
            "同时生成 2-6 个修复目标，目标按逻辑递进：理解问题 → 定位代码 → 实施修复 → 验证结果。\n"
            "Issue 中提到的文件/函数应在目标描述中体现。\n\n"
            "输出严格 JSON（不要输出其他内容）：\n"
            "```json\n"
            "{\n"
            "  \"skill\": \"skill-name\" 或 \"none\",\n"
            "  \"goals\": [\n"
            "    {\"description\": \"目标 1 描述\"},\n"
            "    {\"description\": \"目标 2 描述\"}\n"
            "  ]\n"
            "}\n"
            "```\n\n"
            f"Issue:\n{issue_description}"
        )

    async def select_skill_and_plan(
        self,
        issue_description: str,
        skills_catalog: str,
    ) -> tuple[str, list[dict]]:
        """首次规划：同时选 Skill 和生成目标。"""
        prompt = self._build_skill_and_plan_prompt(issue_description, skills_catalog)
        response = await self.llm.ainvoke(prompt)
        self._extract_usage(response)
        return self._parse_skill_and_plan_json(response.content)

    def _parse_skill_and_plan_json(self, content: str) -> tuple[str, list[dict]]:
        content = content.strip()
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        else:
            brace_match = re.search(r"\{.*\}", content, re.DOTALL)
            if brace_match:
                content = brace_match.group(0)

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return "", [{"description": "执行 Issue 修复", "status": "pending"}]

        if not isinstance(data, dict):
            return "", [{"description": "执行 Issue 修复", "status": "pending"}]

        skill = str(data.get("skill", "")).strip()
        if skill.lower() in ("none", "null", ""):
            skill = ""

        raw_goals = data.get("goals", [])
        if not isinstance(raw_goals, list):
            raw_goals = []

        normalized = []
        for g in raw_goals:
            if isinstance(g, dict) and "description" in g:
                normalized.append({"description": g["description"], "status": "pending"})
        if not normalized:
            normalized = [{"description": "执行 Issue 修复", "status": "pending"}]

        return skill, normalized

    def _build_hierarchical_plan_prompt(
        self,
        issue_description: str,
        existing_goals: list | None = None,
        replan_reason: str = "",
    ) -> str:
        base = (
            "你是代码修复 Agent 的规划器。根据 Issue 生成修复计划。\n\n"
            "输出严格 JSON 格式（不要输出其他内容）：\n"
            "```json\n"
            "[\n"
            '  {"description": "目标1描述"},\n'
            '  {"description": "目标2描述"},\n'
            '  {"description": "目标3描述"}\n'
            "]\n"
            "```\n\n"
            "约束：\n"
            "- 2-6 个目标\n"
            "- 每个目标应是一个清晰的阶段性成果（如：定位问题根因、修复核心逻辑、验证修复正确性）\n"
            "- 目标按逻辑递进：理解问题 → 定位代码 → 实施修复 → 验证结果\n"
            "- Issue 中提到的文件或函数应在目标描述中体现\n"
        )

        if existing_goals and replan_reason:
            completed = [g for g in existing_goals if g.get("status") == "done"]
            base += (
                f"\n\n这是一次重规划。原因：{replan_reason}\n"
                f"已完成的目标（保留不变）：\n"
                f"{json.dumps(completed, ensure_ascii=False, indent=2)}\n"
                "请只输出未完成的新目标列表。"
            )

        base += f"\n\nIssue:\n{issue_description}"
        return base

    async def generate_hierarchical_plan(
        self,
        issue_description: str,
        existing_goals: list | None = None,
        replan_reason: str = "",
    ) -> list[dict]:
        prompt = self._build_hierarchical_plan_prompt(
            issue_description, existing_goals, replan_reason
        )
        response = await self.llm.ainvoke(prompt)
        self._extract_usage(response)
        return self._parse_plan_json(response.content)

    def _parse_plan_json(self, content: str) -> list[dict]:
        content = content.strip()
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        else:
            bracket_match = re.search(r"\[.*\]", content, re.DOTALL)
            if bracket_match:
                content = bracket_match.group(0)

        try:
            goals = json.loads(content)
        except json.JSONDecodeError:
            return [{"description": "执行 Issue 修复", "status": "pending"}]

        if not isinstance(goals, list):
            return [{"description": "执行 Issue 修复", "status": "pending"}]

        normalized = []
        for g in goals:
            if isinstance(g, dict) and "description" in g:
                normalized.append({
                    "description": g["description"],
                    "status": "pending",
                })
        return normalized or [{"description": "执行 Issue 修复", "status": "pending"}]

    # ========== ReAct ==========

    def _build_react_system_prompt(
        self,
        *,
        issue_description: str,
        repo_path: str,
        plan: list[str] | None,
        reflexion_notes: str,
        current_goal: str = "",
        skill_instructions: str = "",
        skill_priority_tools: list[str] | None = None,
        skill_allowed_tools: list[str] | None = None,
    ) -> str:
        latest_plan = "\n".join(plan or []) or "暂无计划"
        reflection = reflexion_notes or "暂无"
        goal_context = ""
        if current_goal:
            goal_context = f"\n当前目标：{current_goal}\n"

        skill_section = ""
        if skill_instructions:
            skill_section = (
                "\n\n========== 当前 Skill 专属工作流（必须遵守） ==========\n"
                f"{skill_instructions}\n"
                "========== Skill 工作流结束 ==========\n"
            )
            if skill_priority_tools:
                skill_section += (
                    f"\n本任务优先使用工具：{', '.join(skill_priority_tools)}。\n"
                )
            if skill_allowed_tools:
                skill_section += (
                    f"本任务允许使用工具：{', '.join(skill_allowed_tools)}。\n"
                    "调用列表外的工具属于违规，必须避免。\n"
                )

        return (
            "你是代码修复 Agent，负责通过工具调用推进仓库问题的修复。\n\n"
            "核心原则：\n"
            "- 行动优先：每轮必须调用工具或输出终止标记，禁止空谈方案\n"
            "- 证据驱动：所有结论必须基于工具返回的实际内容，不要猜测\n"
            "- 信任工具：工具结果与假设冲突时，调整假设而非忽略结果\n\n"
            "行为规范：\n"
            "1. 仓库已在本地，不要调用 git_clone_repo\n"
            "2. 优先检查 Issue 中明确提到的文件、函数、报错信息\n"
            "3. 优先使用高信息增益工具：read_file、search_code、list_files、run_pytest\n"
            "4. 修改代码后立即验证（读取修改后的文件或运行测试）\n"
            "5. 调用工具前用一句话说明假设和预期\n\n"
            "Git 约束：\n"
            "- 不要执行 git add / git commit / git push\n"
            "- 修复完成后保留工作区或暂存区 diff，提交和推送由外层流程处理\n\n"
            "终止标记：\n"
            "- 修复完成且已验证 → 输出 TASK_SUCCESS\n"
            "- 确认无法继续推进 → 输出 TASK_FAILED\n"
            "- 当前目标完成 → 输出 GOAL_DONE\n\n"
            f"仓库路径：{repo_path}\n"
            f"任务描述：\n{issue_description}\n\n"
            f"执行计划：\n{latest_plan}\n\n"
            f"最近反思：\n{reflection}"
            f"{goal_context}"
            f"{skill_section}"
        )

    async def run_react(
        self,
        messages: list,
        issue_description: str = "",
        repo_path: str = "",
        plan: list | None = None,
        reflexion_notes: str = "",
        current_goal: str = "",
        skill_instructions: str = "",
        skill_priority_tools: list[str] | None = None,
        skill_allowed_tools: list[str] | None = None,
    ):
        sys_prompt = SystemMessage(
            content=self._build_react_system_prompt(
                issue_description=issue_description,
                repo_path=repo_path,
                plan=plan,
                reflexion_notes=reflexion_notes,
                current_goal=current_goal,
                skill_instructions=skill_instructions,
                skill_priority_tools=skill_priority_tools,
                skill_allowed_tools=skill_allowed_tools,
            )
        )
        llm_with_tools = self._llm_for_tools(skill_allowed_tools)
        response = await llm_with_tools.ainvoke([sys_prompt] + messages)
        self._extract_usage(response)
        return response

    async def reflect_on_failure(self, trajectory: list, current_goal: str = "") -> str:
        recent = trajectory[-6:]
        history_lines = []
        for item in recent:
            item_type = item.get("type", "unknown")
            content = str(item.get("content", ""))[:200]
            tool_calls = item.get("tool_calls", [])
            if tool_calls:
                tools_desc = ", ".join(c.get("name", "?") for c in tool_calls[:3])
                history_lines.append(f"[{item_type}] 调用工具: {tools_desc}")
            elif content:
                history_lines.append(f"[{item_type}] {content}")

        history_text = "\n".join(history_lines)
        goal_context = ""
        if current_goal:
            goal_context = f"当前目标：{current_goal}\n"

        prompt = (
            "分析以下执行轨迹，诊断为什么没有有效推进，并给出具体的下一步动作。\n\n"
            f"{goal_context}"
            f"最近轨迹：\n{history_text}\n\n"
            "输出格式（每项一行，保持简洁）：\n"
            "卡住原因: ...\n"
            "缺失信息: ...\n"
            "是否偏离目标: 是/否\n"
            "下一步动作: [具体工具名] + [具体参数描述]"
        )
        response = await self.llm.ainvoke(prompt)
        self._extract_usage(response)
        return response.content

    async def verify_issue_resolved(self, issue_description: str, diff_output: str) -> dict[str, str]:
        prompt = (
            "判断以下代码修改是否正确解决了 Issue 中描述的问题。\n\n"
            "判断标准：\n"
            "- 修改是否针对了 Issue 的根本原因（而非表面症状）\n"
            "- 修改是否完整（没有遗漏的文件或逻辑分支）\n"
            "- 修改是否可能引入新问题\n\n"
            f"Issue:\n{issue_description}\n\n"
            f"Git Diff:\n{diff_output[:3000]}\n\n"
            "严格按 JSON 格式输出：\n"
            "```json\n"
            '{"resolved": true/false, "reason": "一句话判断理由"}\n'
            "```"
        )
        response = await self.llm.ainvoke(prompt)
        self._extract_usage(response)
        return self._parse_verify_json(response.content)

    def _parse_verify_json(self, content: str) -> dict[str, str]:
        content = content.strip()
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        else:
            brace_match = re.search(r"\{.*\}", content, re.DOTALL)
            if brace_match:
                content = brace_match.group(0)
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            return {"resolved": False, "reason": "无法解析验证结果"}
        return {
            "resolved": bool(result.get("resolved", False)),
            "reason": result.get("reason", ""),
        }

    async def chat(self, user_input):
        return await self.llm.ainvoke(user_input)


def LLM_factory(model_name: str | None = None):
    model_name = model_name or _get_env("MODEL_NAME") or "hunyuan-lite"
    api_key = _get_env("OPENAI_API_KEY")
    base_url = _get_env("OPENAI_BASE_URL")

    _validate_llm_settings(model_name, base_url)

    llm_kwargs = {}
    if "deepseek" in model_name.lower() or (base_url and "deepseek" in base_url.lower()):
        llm_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
        max_tokens=2048,
        **llm_kwargs,
    )

