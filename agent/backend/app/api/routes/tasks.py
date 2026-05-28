from fastapi import APIRouter, HTTPException, Response

from app.schemas.task import (
    EvaluationResult,
    EvaluationTaskCreate,
    EvaluationTaskResponse,
    EvaluationTaskUpdate,
    GitDiffResponse,
    GitPullRequestRequest,
    GitPullRequestResponse,
    GitPushRequest,
    GitPushResponse,
    TaskMessageCreate,
    TaskMessageList,
    TaskRunRequest,
)
from app.services.evaluation_service import evaluation_service
from app.services.task_service import task_service

router = APIRouter()


@router.get("/", response_model=list[EvaluationTaskResponse])
def list_tasks() -> list[EvaluationTaskResponse]:
    return task_service.list_tasks()


@router.post("/", response_model=EvaluationTaskResponse)
async def create_task(payload: EvaluationTaskCreate) -> EvaluationTaskResponse:
    task = task_service.create_task(payload)
    if payload.auto_start:
        try:
            record = await evaluation_service.run(
                task.id,
                TaskRunRequest(mode=task.config.run_mode, reset=True),
            )
            refreshed = task_service.get_task(record.id)
            if refreshed is not None:
                return refreshed
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task


@router.get("/{task_id}", response_model=EvaluationTaskResponse)
def get_task(task_id: str) -> EvaluationTaskResponse:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=EvaluationTaskResponse)
def update_task(task_id: str, payload: EvaluationTaskUpdate) -> EvaluationTaskResponse:
    task = task_service.update_task(task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if payload.config is not None:
        evaluation_service.clear_task_state(task_id)
    return task


@router.delete("/{task_id}")
def delete_task(task_id: str) -> dict[str, str]:
    evaluation_service.clear_task_state(task_id)
    deleted = task_service.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}


@router.post("/{task_id}/run", response_model=EvaluationTaskResponse)
async def run_task(
    task_id: str,
    payload: TaskRunRequest | None = None,
) -> EvaluationTaskResponse:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        updated_record = await evaluation_service.run(task_id, payload or TaskRunRequest())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    refreshed = task_service.get_task(updated_record.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return refreshed


@router.get("/{task_id}/results", response_model=EvaluationResult)
def get_task_result(task_id: str) -> EvaluationResult:
    result = evaluation_service.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


@router.get("/{task_id}/messages", response_model=TaskMessageList)
def get_task_messages(task_id: str) -> TaskMessageList:
    messages = evaluation_service.get_messages(task_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return messages


@router.post("/{task_id}/messages", response_model=TaskMessageList)
def submit_task_message(task_id: str, payload: TaskMessageCreate) -> TaskMessageList:
    try:
        messages = evaluation_service.submit_message(task_id, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if messages is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return messages


@router.get("/{task_id}/diff", response_model=GitDiffResponse)
def get_task_diff(task_id: str) -> GitDiffResponse:
    try:
        diff = evaluation_service.get_git_diff(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if diff is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return diff


@router.get("/{task_id}/report")
def download_task_report(task_id: str) -> Response:
    report = evaluation_service.get_fix_report(task_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return Response(
        content=report.markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{report.file_name}"',
        },
    )


@router.post("/{task_id}/push", response_model=GitPushResponse)
def push_task_changes(
    task_id: str,
    payload: GitPushRequest | None = None,
) -> GitPushResponse:
    try:
        response = evaluation_service.push_changes(task_id, payload or GitPushRequest())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return response


@router.post("/{task_id}/pull-request", response_model=GitPullRequestResponse)
def create_task_pull_request(
    task_id: str,
    payload: GitPullRequestRequest | None = None,
) -> GitPullRequestResponse:
    try:
        response = evaluation_service.create_pull_request(
            task_id,
            payload or GitPullRequestRequest(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return response
