from fastapi import APIRouter

from app.api.routes import analytics, metadata, tasks

api_router = APIRouter()
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(metadata.router, prefix="/metadata", tags=["metadata"])
