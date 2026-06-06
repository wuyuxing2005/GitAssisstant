from fastapi import APIRouter

from gitIssueAssitant.RESTAPIAdapter.api.routes import analytics, github, metadata, settings, skills, tasks

api_router = APIRouter()
api_router.include_router(github.router, prefix="", tags=["github"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(metadata.router, prefix="/metadata", tags=["metadata"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])

