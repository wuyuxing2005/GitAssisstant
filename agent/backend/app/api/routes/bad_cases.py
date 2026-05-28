from fastapi import APIRouter, HTTPException

from app.schemas.task import (
    BadCaseCreate,
    BadCaseListResponse,
    BadCaseRecord,
    BadCaseRerunRequest,
    BadCaseUpdate,
    DEFAULT_BAD_CASE_TAGS,
    EvaluationTaskResponse,
    TaskRunRequest,
)
from app.services.bad_case_service import bad_case_service
from app.services.evaluation_service import evaluation_service

router = APIRouter()


@router.get("/", response_model=BadCaseListResponse)
def list_bad_cases() -> BadCaseListResponse:
    return BadCaseListResponse(
        items=bad_case_service.list_cases(),
        default_tags=list(DEFAULT_BAD_CASE_TAGS),
    )


@router.get("/{case_id}", response_model=BadCaseRecord)
def get_bad_case(case_id: str) -> BadCaseRecord:
    record = bad_case_service.get(case_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Bad case not found")
    return record


@router.post("/", response_model=BadCaseRecord)
def create_bad_case(payload: BadCaseCreate) -> BadCaseRecord:
    try:
        return bad_case_service.create_from_task(payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{case_id}", response_model=BadCaseRecord)
def update_bad_case(case_id: str, payload: BadCaseUpdate) -> BadCaseRecord:
    record = bad_case_service.update(case_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Bad case not found")
    return record


@router.delete("/{case_id}")
def delete_bad_case(case_id: str) -> dict[str, str]:
    if not bad_case_service.delete(case_id):
        raise HTTPException(status_code=404, detail="Bad case not found")
    return {"message": "Bad case deleted"}


@router.post("/{case_id}/rerun", response_model=EvaluationTaskResponse)
async def rerun_bad_case(
    case_id: str,
    payload: BadCaseRerunRequest | None = None,
) -> EvaluationTaskResponse:
    request = payload or BadCaseRerunRequest()
    try:
        task = bad_case_service.rerun(case_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="Bad case not found")
    if request.auto_start:
        await evaluation_service.run(
            task.id,
            TaskRunRequest(mode=task.config.run_mode, reset=True),
        )
    return task
