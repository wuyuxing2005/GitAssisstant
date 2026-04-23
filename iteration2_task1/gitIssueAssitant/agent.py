import os

from openai import OpenAI
from dataclasses import dataclass
from typing import List
import json
import re


from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from .agent_state import AgentState
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
            " 不能填写 API Key。"
        )

    if model_name == "hunyuan-lite" and not base_url:
        raise RuntimeError(
            "MODEL_NAME=hunyuan-lite 但未配置 OPENAI_BASE_URL。"
            " 如果你使用 OpenAI 官方接口，请把 MODEL_NAME 改成可用的 OpenAI 模型；"
            " 如果你使用兼容网关，请补充 OPENAI_BASE_URL。"
        )


class Agent:
    def __init__(self, llm: ChatOpenAI, tools=AGENT_TOOLS):
        """
        llm: 基础的大模型实例 (如 ChatOpenAI)
        tools: 第二组提供的工具列表
        """
        # 纯净版模型，用于生成文本（规划、反思）
        self.llm = llm

        # 武装版模型，给 LLM 绑定工具（用于 ReAct 执行）
        self.llm_with_tools = llm.bind_tools(tools)

    async def generate_plan(self, issue_description: str) -> str:
        """规划能力"""
        prompt = f"你是一个高级工程师。针对以下Issue，请给出分步的排查和修复计划：\n{issue_description}"
        response = await self.llm.ainvoke(prompt)
        return response.content

    async def run_react(
        self,
        messages: list,
        issue_description: str = "",
        repo_path: str = "",
        plan: list | None = None,
        reflexion_notes: str = "",
    ):
        """ReAct 能力：根据历史消息决定下一步动作（可能调用工具，可能输出文本）"""
        plan_text = "\n".join(plan or [])
        sys_prompt = SystemMessage(
            content="你是代码修复 Agent。你可以调用工具收集信息并修复代码。"
                    "仓库已经在本地可用，默认不要再次调用 git_clone_repo，只有确认本地仓库缺失时才允许克隆。"
                    "所有读写、搜索、测试工具默认都以当前 repo_root 为基准，不需要自己拼路径。"
                    "如需确认路径上下文，先调用 current_repo_info。"
                    "优先先阅读仓库和相关文件，再做修改，并在可能时运行测试验证。"
                    "如果确认缺少文件，应优先直接调用 write_file 创建文件，而不是只给操作建议。"
                    "完成修改后，不要立刻宣称成功；应继续检查仓库当前状态是否已经满足 issue 要求。"
                    "例如 issue 说缺少 1.cpp，那么只有在仓库里实际存在 1.cpp 时才算成功。"
                    "一旦你已经完成了实际文件修改（例如成功调用 write_file、replace_in_file 或 patch_file），"
                    "你的下一条回复必须明确说明修改结果，并包含精确字样 'TASK_SUCCESS'。"
                    "修改完成后不要继续输出泛泛而谈的建议、排查步骤或求助说明。"
                    "如果你认为修复已经完成，请在回复中包含 'TASK_SUCCESS'。"
                    "如果穷尽手段依然无法解决，请在回复中包含 'TASK_FAILED'。\n\n"
                    f"当前仓库根目录：{repo_path}\n"
                    f"当前任务：{issue_description}\n"
                    "如果你暂时不调用工具，也必须明确给出下一步并尽快结束；不要只重复计划。\n"
                    f"当前计划：\n{plan_text or '暂无计划'}\n"
                    f"反思笔记：{reflexion_notes or '暂无'}"
        )
        # 将系统提示词与历史消息拼接
        full_messages = [sys_prompt] + messages
        # 注意：这里使用的是带工具的模型
        response = await self.llm_with_tools.ainvoke(full_messages)
        return response

    async def reflect_on_failure(self, trajectory: list) -> str:
        history_text = "\n".join([str(m) for m in trajectory])

        prompt = f"""
        之前的修复尝试未能成功，或者陷入死循环。
        以下是历史执行轨迹：
        {history_text}
        请分析失败原因，并给出新的排查方向。
        """
        response = await self.llm.ainvoke(prompt)
        return response.content

    async def chat(self, user_input):
        response = await self.llm.ainvoke(user_input)
        return response
# 直接使用 LangChain 提供的 ChatOpenAI


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
        max_tokens=2048
    )
