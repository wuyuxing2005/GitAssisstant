from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agent Evaluation Platform API"
    database_url: str = (
        "postgresql+psycopg://postgres:123456@localhost:5432/LLMJUDGE"
    )

    # Ragas 配置
    ragas_dataset_dir: str = "./data/eval_datasets"

    # LLM 配置 (支持 OpenAI 兼容接口)
    # 可选值：
    # - OpenAI: base_url="https://api.openai.com/v1", model="gpt-4o-mini"
    # - DeepSeek: base_url="https://api.deepseek.com/v1", model="deepseek-chat"
    # - GLM/Zhipu: base_url="https://open.bigmodel.cn/api/paas/v4", model="glm-4"
    ragas_llm_model: str = "gpt-4o-mini"
    ragas_llm_api_key: str = ""
    ragas_llm_base_url: str = "https://api.openai.com/v1"

    # Embedding 配置 (支持 OpenAI 兼容接口)
    # 可选值：
    # - OpenAI: base_url="https://api.openai.com/v1", model="text-embedding-3-small"
    # - 使用本地 BGE 模型：model="BAAI/bge-small-zh-v1.5" (无需 API key)
    ragas_embedding_model: str = "text-embedding-3-small"
    ragas_embedding_api_key: str = ""
    ragas_embedding_base_url: str = "https://api.openai.com/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENT_EVAL_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
