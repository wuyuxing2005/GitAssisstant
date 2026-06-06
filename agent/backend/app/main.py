from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.services.evaluation_service import evaluation_service

app = FastAPI(
    title="gitIssueAssitant",
    description="用于包装 gitIssueAssitant 任务、执行和结果展示的后端服务。",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("shutdown")
def shutdown_runtime_resources() -> None:
    evaluation_service.shutdown()


app.include_router(api_router, prefix="/api")
