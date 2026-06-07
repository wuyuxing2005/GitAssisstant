from fastapi import APIRouter, HTTPException

from gitIssueAssitant.core.schemas.settings import AppSettingsResponse, AppSettingsUpdate, ModelListResponse
from gitIssueAssitant.core.services.settings_service import settings_service

router = APIRouter()


@router.get("/", response_model=AppSettingsResponse)
def get_settings() -> AppSettingsResponse:
    return settings_service.get_settings()


@router.put("/", response_model=AppSettingsResponse)
def update_settings(payload: AppSettingsUpdate) -> AppSettingsResponse:
    try:
        return settings_service.update_settings(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/models", response_model=ModelListResponse)
def list_models() -> ModelListResponse:
    try:
        return settings_service.list_models()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

