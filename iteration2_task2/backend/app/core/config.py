from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agent Evaluation Platform API"
    database_url: str = (
        "postgresql+psycopg://postgres:123456@localhost:5432/LLMJUDGE"
    )
    ragas_enabled: bool = False
    ragas_dataset_dir: str = "./data/eval_datasets"
    ragas_llm_model: str = "gpt-4o-mini"
    ragas_embedding_model: str = "text-embedding-3-small"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENT_EVAL_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
