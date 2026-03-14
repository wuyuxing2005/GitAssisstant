import json
from openai import OpenAI

from llm import SimpleLLM

llm = SimpleLLM()

resp = llm.generate(
    "Explain what RAG is",
    system="You are an AI researcher"
)

print(resp[0])