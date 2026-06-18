import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gitIssueAssitant.RESTAPIAdapter.api.router import api_router
from gitIssueAssitant.core.services.issue_assistant_service import issue_assistant_service


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


_configure_utf8_stdio()

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
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:6000",
        "http://127.0.0.1:6000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
def recover_interrupted_runtime_tasks() -> None:
    issue_assistant_service.recover_interrupted_tasks()


@app.on_event("shutdown")
def shutdown_runtime_resources() -> None:
    issue_assistant_service.shutdown()


app.include_router(api_router, prefix="/api")


