from fastapi import APIRouter

from app.api.routes import analytics, metadata, tasks, traces, datasets, reports

api_router = APIRouter()
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(metadata.router, prefix="/metadata", tags=["metadata"])
api_router.include_router(traces.router, prefix="/traces", tags=["traces"])
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(reports.router, prefix="", tags=["reports"])
