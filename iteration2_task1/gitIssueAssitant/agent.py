from __future__ import annotations

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

    def _build_plan_prompt(self, issue_description: str) -> str:
        return (
            "你是一个代码修复 Agent 的规划器。\n"
            "请基于下面的 Issue 输出 3-6 条简洁的排查/修复步骤。\n"
            "要求：\n"
            "1. 只输出步骤，不要长篇解释。\n"
            "2. 优先包含“阅读相关文件 / 搜索代码 / 修改 / 验证”这些动作。\n"
            "3. 如果 Issue 中点名了文件或函数，要优先检查它们。\n\n"
            f"Issue:\n{issue_description}"
        )

    def _build_react_system_prompt(
        self,
        *,
        issue_description: str,
        repo_path: str,
        plan: list[str] | None,
        reflexion_notes: str,
    ) -> str:
        latest_plan = "\n".join(plan or []) or "暂无计划"
        reflection = reflexion_notes or "暂无"
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
            "8. 如果某个工具结果与你的假设冲突，信任工具结果并调整策略。\n\n"
            "输出规则：\n"
            "- 若需要更多证据，优先调用工具，不要只输出泛泛建议。\n"
            "- 若暂时不调用工具，必须给出一个具体且可执行的下一步，不能重复计划。\n"
            "- 不要把未验证的猜测表述成事实。\n\n"
            f"当前仓库根目录：{repo_path}\n"
            f"当前任务：\n{issue_description}\n\n"
            f"当前计划：\n{latest_plan}\n\n"
            f"最近反思：\n{reflection}"
        )

    async def generate_plan(self, issue_description: str) -> str:
        response = await self.llm.ainvoke(self._build_plan_prompt(issue_description))
        return response.content

    async def run_react(
        self,
        messages: list,
        issue_description: str = "",
        repo_path: str = "",
        plan: list | None = None,
        reflexion_notes: str = "",
    ):
        sys_prompt = SystemMessage(
            content=self._build_react_system_prompt(
                issue_description=issue_description,
                repo_path=repo_path,
                plan=plan,
                reflexion_notes=reflexion_notes,
            )
        )
        return await self.llm_with_tools.ainvoke([sys_prompt] + messages)

    async def reflect_on_failure(self, trajectory: list) -> str:
        history_text = "\n".join(str(item) for item in trajectory[-10:])
        prompt = (
            "你是代码修复流程的反思器。\n"
            "下面是最近的执行轨迹。请分析为什么没有有效推进，并给出更好的下一步。\n\n"
            f"{history_text}\n\n"
            "请严格按下面格式输出，保持简洁：\n"
            "失败原因: ...\n"
            "缺失证据: ...\n"
            "下一步工具: ...\n"
            "下一步目的: ..."
        )
        response = await self.llm.ainvoke(prompt)
        return response.content

    async def chat(self, user_input):
        return await self.llm.ainvoke(user_input)


def LLM_factory():
    model_name = _get_env("MODEL_NAME") or "hunyuan-lite"
    api_key = _get_env("OPENAI_API_KEY")
    base_url = _get_env("OPENAI_BASE_URL")

    _validate_llm_settings(model_name, base_url)

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
        max_tokens=2048,
    )
