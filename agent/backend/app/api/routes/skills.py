from fastapi import APIRouter, HTTPException

from app.schemas.task import SkillEnabledUpdate, SkillListResponse, SkillRecord
from app.services.skill_service import skill_service

router = APIRouter()


@router.get("/", response_model=SkillListResponse)
def list_skills() -> SkillListResponse:
    return SkillListResponse(items=skill_service.list_skills())


@router.put("/{name}/enabled", response_model=SkillRecord)
def update_skill_enabled(name: str, payload: SkillEnabledUpdate) -> SkillRecord:
    skill = skill_service.set_enabled(name, payload.enabled)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill
