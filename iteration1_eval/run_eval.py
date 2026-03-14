import json
from openai import OpenAI

from llm import SimpleLLM
from evaluator import Evaluator
llm = SimpleLLM()

# resp = llm.generate(
#     "Explain what RAG is",
#     system="You are an AI researcher"
# )


# print(resp[0])

Evaluator = Evaluator(metrics=[], llm=llm)
