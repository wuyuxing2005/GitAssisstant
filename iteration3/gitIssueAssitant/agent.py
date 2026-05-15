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
        self.llm_with_tools = llm.bind_tools(tools)

    # ========== 分层规划 ==========

    def _build_hierarchical_plan_prompt(
        self,
        issue_description: str,
        existing_goals: list | None = None,
        replan_reason: str = "",
    ) -> str:
        base = (
            "你是代码修复 Agent 的规划器。请将问题分解为 2-5 个高层目标，"
            "每个目标包含 1-4 个具体子步骤。\n\n"
            "输出严格 JSON 格式（不要输出其他内容）：\n"
            "```json\n"
            "[\n"
            '  {"description": "目标描述", "sub_steps": ["子步骤1", "子步骤2"]}\n'
            "]\n"
            "```\n\n"
            "规则：\n"
            "- 子步骤必须是可执行的动作（读文件、搜索代码、修改文件、运行测试）\n"
            "- 如果 Issue 中点名了文件或函数，优先检查它们\n"
            "- 目标之间应有逻辑递进关系（理解 → 定位 → 修复 → 验证）\n"
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
            return [{"description": "执行 Issue 修复", "sub_steps": ["分析问题", "修改代码", "验证结果"]}]#fall back

        if not isinstance(goals, list):
            return [{"description": "执行 Issue 修复", "sub_steps": ["分析问题", "修改代码", "验证结果"]}]

        normalized = []
        for g in goals:
            if isinstance(g, dict) and "description" in g:
                normalized.append({
                    "description": g["description"],
                    "sub_steps": g.get("sub_steps", []),
                    "status": "pending",
                    "current_sub_step_index": 0,
                })
        return normalized or [{"description": "执行 Issue 修复", "sub_steps": ["分析问题", "修改代码", "验证结果"], "status": "pending", "current_sub_step_index": 0}]

    # ========== 结构化 CoT ==========

    def _build_cot_prompt(
        self,
        current_goal: str,
        current_sub_step: str,
        reflexion_notes: str,
        trajectory_summary: str,
    ) -> str:
        return (
            "在执行下一步之前，请输出你的结构化思考。\n"
            "严格按以下 JSON 格式输出（不要输出其他内容）：\n"
            "```json\n"
            "{\n"
            '  "hypothesis": "当前对问题根因的假设",\n'
            '  "expected_result": "执行下一步后预期看到什么结果",\n'
            '  "tool_rationale": "选择下一个工具/动作的理由"\n'
            "}\n"
            "```\n\n"
            f"当前目标：{current_goal}\n"
            f"当前子步骤：{current_sub_step}\n"
            f"最近反思：{reflexion_notes or '暂无'}\n"
            f"最近执行摘要：{trajectory_summary or '暂无'}"
        )

    async def generate_cot_thought(
        self,
        current_goal: str,
        current_sub_step: str,
        reflexion_notes: str = "",
        trajectory_summary: str = "",
    ) -> dict[str, str]:
        prompt = self._build_cot_prompt(
            current_goal, current_sub_step, reflexion_notes, trajectory_summary
        )
        response = await self.llm.ainvoke(prompt)
        return self._parse_cot_json(response.content)

    def _parse_cot_json(self, content: str) -> dict[str, str]:
        content = content.strip()
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        else:
            brace_match = re.search(r"\{.*\}", content, re.DOTALL)
            if brace_match:
                content = brace_match.group(0)

        try:
            thought = json.loads(content)
        except json.JSONDecodeError:
            return {"hypothesis": "无法解析", "expected_result": "继续推进", "tool_rationale": "尝试下一步"}

        return {
            "hypothesis": thought.get("hypothesis", ""),
            "expected_result": thought.get("expected_result", ""),
            "tool_rationale": thought.get("tool_rationale", ""),
        }

    # ========== ReAct ==========

    def _build_react_system_prompt(
        self,
        *,
        issue_description: str,
        repo_path: str,
        plan: list[str] | None,
        reflexion_notes: str,
        current_goal: str = "",
        current_sub_step: str = "",
        last_thought: dict[str, str] | None = None,
    ) -> str:
        latest_plan = "\n".join(plan or []) or "暂无计划"
        reflection = reflexion_notes or "暂无"
        goal_context = ""
        if current_goal:
            goal_context = f"\n当前目标：{current_goal}\n当前子步骤：{current_sub_step}\n"

        thought_context = ""
        if last_thought and last_thought.get("hypothesis"):
            thought_context = (
                f"\n你的思考：\n"
                f"  假设：{last_thought.get('hypothesis', '')}\n"
                f"  预期结果：{last_thought.get('expected_result', '')}\n"
                f"  工具选择理由：{last_thought.get('tool_rationale', '')}\n"
            )

        return (
            "你是一个负责真实修复仓库问题的代码 Agent。\n\n"
            "你的首要目标不是讨论方案，而是基于仓库证据推进修复。\n\n"
            "工作规则：\n"
            "1. 仓库已经在本地可用，默认不要再次调用 git_clone_repo。\n"
            "2. 在声称任何代码结论前，先使用工具读取或搜索仓库；不要凭空猜测。\n"
            "3. 如果 Issue 明确提到文件名、函数名、报错或测试名，优先直接检查这些对象。\n"
            "4. 当你上一轮没有使用工具且没有得到验证证据时，这一轮不要重复计划，必须推进下一步调查或修改。\n"
            "5. 如果你已经完成实际修改，下一条回复应明确总结修改结果，并包含 TASK_SUCCESS。\n"
            "6. 只有在确认无法继续推进时才输出 TASK_FAILED；不要因为一次搜索失败就放弃。\n"
            "7. 优先做高信息增益动作：read_file、search_code、list_files、run_pytest、replace_in_file、patch_file。\n"
            "8. 如果某个工具结果与你的假设冲突，信任工具结果并调整策略。\n"
            "9. 完成当前子步骤后，在回复中包含 SUB_STEP_DONE 标记。\n\n"
            "输出规则：\n"
            "- 若需要更多证据，优先调用工具，不要只输出泛泛建议。\n"
            "- 若暂时不调用工具，必须给出一个具体且可执行的下一步，不能重复计划。\n"
            "- 不要把未验证的猜测表述成事实。\n\n"
            f"当前仓库根目录：{repo_path}\n"
            f"当前任务：\n{issue_description}\n\n"
            f"当前计划：\n{latest_plan}\n\n"
            f"最近反思：\n{reflection}"
            f"{goal_context}"
            f"{thought_context}"
        )

    async def generate_plan(self, issue_description: str) -> str:
        """兼容旧接口：生成文本计划"""
        goals = await self.generate_hierarchical_plan(issue_description)
        lines = []
        for i, g in enumerate(goals, 1):
            lines.append(f"{i}. {g['description']}")
            for j, s in enumerate(g.get("sub_steps", []), 1):
                lines.append(f"   {i}.{j} {s}")
        return "\n".join(lines)

    async def run_react(
        self,
        messages: list,
        issue_description: str = "",
        repo_path: str = "",
        plan: list | None = None,
        reflexion_notes: str = "",
        current_goal: str = "",
        current_sub_step: str = "",
        last_thought: dict[str, str] | None = None,
    ):
        sys_prompt = SystemMessage(
            content=self._build_react_system_prompt(
                issue_description=issue_description,
                repo_path=repo_path,
                plan=plan,
                reflexion_notes=reflexion_notes,
                current_goal=current_goal,
                current_sub_step=current_sub_step,
                last_thought=last_thought,
            )
        )
        return await self.llm_with_tools.ainvoke([sys_prompt] + messages)

    async def reflect_on_failure(self, trajectory: list, current_goal: str = "", current_sub_step: str = "") -> str:
        history_text = "\n".join(str(item) for item in trajectory[-10:])
        goal_context = ""
        if current_goal:
            goal_context = f"\n当前目标：{current_goal}\n当前子步骤：{current_sub_step}\n"

        prompt = (
            "你是代码修复流程的反思器。\n"
            "下面是最近的执行轨迹。请分析为什么没有有效推进，并给出更好的下一步。\n\n"
            f"{history_text}\n"
            f"{goal_context}\n"
            "请严格按下面格式输出，保持简洁：\n"
            "失败原因: ...\n"
            "缺失证据: ...\n"
            "是否需要重规划: 是/否\n"
            "下一步工具: ...\n"
            "下一步目的: ..."
        )
        response = await self.llm_with_tools.ainvoke(prompt)
        return response.content

    async def chat(self, user_input):
        return await self.llm.ainvoke(user_input)


def LLM_factory():
    model_name = _get_env("MODEL_NAME") or "hunyuan-lite"
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
