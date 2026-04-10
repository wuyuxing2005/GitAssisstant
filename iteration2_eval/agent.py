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
class Agent:
    def __init__(self, llm:ChatOpenAI, tools=AGENT_TOOLS):
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

    async def run_react(self, messages: list):
        """ReAct 能力：根据历史消息决定下一步动作（可能调用工具，可能输出文本）"""
        sys_prompt = SystemMessage(
            content="你是代码修复 Agent。你可以调用工具收集信息并修复代码。"
                    "如果你认为修复已经完成，请在回复中包含 'TASK_SUCCESS'。"
                    "如果穷尽手段依然无法解决，请在回复中包含 'TASK_FAILED'。"
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
    return ChatOpenAI(
        model=os.getenv("MODEL_NAME", "hunyuan-lite"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0.1,
        max_tokens=2048
    )

# @dataclass
# class SimpleLLM:
#     model: str = "hunyuan-lite"
#     temperature: float = 0.1

#     def __post_init__(self):
#         self.client = OpenAI(
#         api_key="sk-LKBTrcFAI8TAl0AuNuEsymgBxrGBQvGzc9UcUCALil4SJm1Z",
#         base_url="https://api.hunyuan.cloud.tencent.com/v1"
#         )

#     def generate(
#         self,
#         user_prompt: str,
#         system_prompt: str | None = None,
#         max_tokens: int = 512,
#         n: int = 1,
#     ) -> List[str]:
#         """生成文本"""
#         resp = self.generate_raw(user_prompt,system_prompt,max_tokens,n)
#         return [c.message.content for c in resp.choices]
    
#     def generate_raw(self,
#         user_prompt: str,
#         system_prompt: str | None = None,
#         max_tokens: int = 512,
#         n: int = 1,
#         ) -> List[str]:
#         """生成文本"""
#         messages = []
#         if system_prompt:
#             messages.append({"role": "system", "content": system_prompt})
#         messages.append({"role": "user", "content": user_prompt})
#         resp = self.client.chat.completions.create(
#             model=self.model,
#             messages=messages,
#             temperature=self.temperature,
#             max_tokens=max_tokens,
#             n=n,
#         )
#         return resp

# class AsyncSimpleLLM(SimpleLLM):

#     def __post_init__(self):
#         self.client = AsyncOpenAI()

#     async def agenerate(self,
#         user_prompt: str,
#         system_prompt: str | None = None,
#         max_tokens: int = 512,
#         n: int = 1,
#         ) -> List[str]:
#         messages = []
#         if system_prompt:
#             messages.append({"role": "system", "content": system_prompt})

#         messages.append({"role": "user", "content": user_prompt})
#         resp = await self.client.chat.completions.create(
#             model=self.model,
#             messages=messages,
#             temperature=self.temperature,
#             max_tokens=max_tokens,
#             n=n,
#         )

#         return [c.message.content for c in resp.choices]

# # utils
# def extract_statements(answer, llm):

#     prompt = f"""
#     Break the following text into atomic factual statements.
#     Each statement should be a single fact that can be verified independently.
#     One line per statement.
#     Text:
#     {answer}

#     Statements:
#     """

#     resp = llm.generate(prompt)

#     statements = parse_list(resp)

#     return statements

# def parse_list(text):
#     """
#     Parses a text containing a list of statements and returns them as a list.
#     Assumes statements are separated by newlines or numbered.
#     """
#     lines = text.strip().split('\n')
#     statements = []
#     for line in lines:
#         # Remove numbering or bullet points
#         statement = line.strip()
#         if statement:
#             statement = statement.lstrip('0123456789. ').strip('- ')
#             if statement:
#                 statements.append(statement)
#     return statements


