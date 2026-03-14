from openai import OpenAI
from dataclasses import dataclass
from typing import List


from openai import AsyncOpenAI

@dataclass
class SimpleLLM:
    model: str = "hunyuan-lite"
    temperature: float = 0.1

    def __post_init__(self):
        self.client = OpenAI(
        api_key="sk-LKBTrcFAI8TAl0AuNuEsymgBxrGBQvGzc9UcUCALil4SJm1Z",
        base_url="https://api.hunyuan.cloud.tencent.com/v1"
        )

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 512,
        n: int = 1,
    ) -> List[str]:
        """生成文本"""

        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=max_tokens,
            n=n,
        )

        return [c.message.content for c in resp.choices]
    

class AsyncSimpleLLM(SimpleLLM):

    def __post_init__(self):
        self.client = AsyncOpenAI()

    async def agenerate(self, prompt: str):

        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )

        return resp.choices[0].message.content

# utils
def extract_statements(answer, llm):

    prompt = f"""
    Break the following text into atomic factual statements.
    Each statement should be a single fact that can be verified independently.
    One line per statement.
    Text:
    {answer}

    Statements:
    """

    resp = llm.generate(prompt)

    statements = parse_list(resp)

    return statements

def parse_list(text):
    """
    Parses a text containing a list of statements and returns them as a list.
    Assumes statements are separated by newlines or numbered.
    """
    lines = text.strip().split('\n')
    statements = []
    for line in lines:
        # Remove numbering or bullet points
        statement = line.strip()
        if statement:
            statement = statement.lstrip('0123456789. ').strip('- ')
            if statement:
                statements.append(statement)
    return statements