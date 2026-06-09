import asyncio

from fastapi import APIRouter, HTTPException, Response

from gitIssueAssitant.core.schemas.task import (
    AgentTrace,
    TaskResult,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    GitDiffResponse,
    GitHubIssueCommentRequest,
    GitHubIssueCommentResponse,
    GitHubIssueInfo,
    GitHubIssueStateRequest,
    GitHubIssueStateResponse,
    GitPullRequestRequest,
    GitPullRequestResponse,
    GitPushRequest,
    GitPushResponse,
    TaskMessageCreate,
    TaskMessageList,
    TaskRunRequest,
)
from gitIssueAssitant.core.services.github_issue_service import GitHubIssueError, github_issue_service
from gitIssueAssitant.core.services.issue_assistant_service import issue_assistant_service

router = APIRouter()


@router.get("/", response_model=list[TaskResponse])
def list_tasks() -> list[TaskResponse]:
    return issue_assistant_service.list_tasks()


@router.post("/", response_model=TaskResponse)
async def create_task(payload: TaskCreate) -> TaskResponse:
    task = issue_assistant_service.create_task(payload)
    if payload.auto_start:
        try:
            record = await issue_assistant_service.run_task(
                task.id,
                TaskRunRequest(mode=task.config.run_mode, reset=True),
            )
            refreshed = issue_assistant_service.get_task(record.id)
            if refreshed is not None:
                return refreshed
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    task = issue_assistant_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, payload: TaskUpdate) -> TaskResponse:
    task = issue_assistant_service.update_task(task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
def delete_task(task_id: str) -> dict[str, str]:
    deleted = issue_assistant_service.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}


@router.post("/{task_id}/run", response_model=TaskResponse)
async def run_task(
    task_id: str,
    payload: TaskRunRequest | None = None,
) -> TaskResponse:
    task = issue_assistant_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        updated_record = await issue_assistant_service.run_task(task_id, payload or TaskRunRequest())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    refreshed = issue_assistant_service.get_task(updated_record.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return refreshed


@router.post("/{task_id}/sandbox/terminate", response_model=TaskResponse)
def terminate_sandbox_unavailable_task(task_id: str) -> TaskResponse:
    task = issue_assistant_service.terminate_after_sandbox_unavailable(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    refreshed = issue_assistant_service.get_task(task.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return refreshed


@router.get("/{task_id}/results", response_model=TaskResult)
def get_task_result(task_id: str) -> TaskResult:
    result = issue_assistant_service.get_task_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


@router.get("/{task_id}/trace", response_model=AgentTrace)
def get_task_trace(task_id: str) -> AgentTrace:
    trace = issue_assistant_service.get_task_trace(task_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@router.get("/{task_id}/messages", response_model=TaskMessageList)
def get_task_messages(task_id: str) -> TaskMessageList:
    messages = issue_assistant_service.get_task_messages(task_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return messages


@router.post("/{task_id}/messages", response_model=TaskMessageList)
async def submit_task_message(task_id: str, payload: TaskMessageCreate) -> TaskMessageList:
    try:
        messages = await asyncio.to_thread(
            issue_assistant_service.submit_task_message,
            task_id,
            payload,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if messages is None:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        await issue_assistant_service.run_task(task_id, TaskRunRequest(mode="auto"))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    refreshed = await asyncio.to_thread(issue_assistant_service.get_task_messages, task_id)
    return refreshed or messages


@router.get("/{task_id}/diff", response_model=GitDiffResponse)
def get_task_diff(task_id: str) -> GitDiffResponse:
    try:
        diff = issue_assistant_service.get_task_git_diff(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if diff is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return diff


@router.get("/{task_id}/report")
def download_task_report(task_id: str) -> Response:
    report = issue_assistant_service.get_task_fix_report(task_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return Response(
        content=report.markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{report.file_name}"',
        },
    )


@router.get("/{task_id}/issue", response_model=GitHubIssueInfo)
def get_task_issue(task_id: str, include_comments: bool = False) -> GitHubIssueInfo:
    try:
        issue = github_issue_service.get_issue(task_id, include_comments=include_comments)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitHubIssueError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if issue is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return issue


@router.post("/{task_id}/issue/comment", response_model=GitHubIssueCommentResponse)
def create_task_issue_comment(
    task_id: str,
    payload: GitHubIssueCommentRequest,
) -> GitHubIssueCommentResponse:
    try:
        response = github_issue_service.create_comment(task_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitHubIssueError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return response


@router.patch("/{task_id}/issue/state", response_model=GitHubIssueStateResponse)
def update_task_issue_state(
    task_id: str,
    payload: GitHubIssueStateRequest,
) -> GitHubIssueStateResponse:
    try:
        response = github_issue_service.update_state(task_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitHubIssueError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return response


@router.post("/{task_id}/push", response_model=GitPushResponse)
def push_task_changes(
    task_id: str,
    payload: GitPushRequest | None = None,
) -> GitPushResponse:
    try:
        response = issue_assistant_service.push_task_changes(task_id, payload or GitPushRequest())
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
        response = issue_assistant_service.create_task_pull_request(
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


