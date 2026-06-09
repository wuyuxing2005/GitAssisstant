from fastapi import APIRouter, HTTPException

from gitIssueAssitant.core.schemas.task import SkillCreateRequest, SkillEnabledUpdate, SkillListResponse, SkillRecord
from gitIssueAssitant.core.services.skill_service import skill_service

router = APIRouter()


@router.get("/", response_model=SkillListResponse)
def list_skills() -> SkillListResponse:
    return SkillListResponse(items=skill_service.list_skills())


@router.post("/", response_model=SkillRecord, status_code=201)
def create_skill(payload: SkillCreateRequest) -> SkillRecord:
    try:
        return skill_service.create_skill(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{name}/enabled", response_model=SkillRecord)
def update_skill_enabled(name: str, payload: SkillEnabledUpdate) -> SkillRecord:
    skill = skill_service.set_enabled(name, payload.enabled)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.delete("/{name}", status_code=204)
def delete_skill(name: str) -> None:
    try:
        result = skill_service.delete_skill(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    if result is False:
        raise HTTPException(status_code=403, detail="Skill cannot be deleted")

