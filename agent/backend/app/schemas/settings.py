from pydantic import BaseModel, Field


class AppSettingsResponse(BaseModel):
    openai_api_key_set: bool = False
    github_token_set: bool = False
    openai_api_key: str = ""
    github_token: str = ""
    openai_base_url: str = ""
    model_name: str = ""
    clone_root: str = ""
    env_path: str = ""


class AppSettingsUpdate(BaseModel):
    openai_api_key: str | None = Field(default=None)
    github_token: str | None = Field(default=None)
    openai_base_url: str | None = Field(default=None)
    model_name: str | None = Field(default=None)
    clone_root: str | None = Field(default=None)


class ModelListResponse(BaseModel):
    models: list[str] = Field(default_factory=list)
