from fastapi import FastAPI

from app.api.router import api_router

app = FastAPI(
    title="Agent 应用评估平台 API",
    description="用于管理评测任务、执行评测并展示分析结果的后端骨架。",
    version="0.1.0",
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")
