from uuid import uuid4

from gitIssueAssitant.core.repositories.task_repository import task_repository
from pathlib import Path
from gitIssueAssitant.core.schemas.task import (
    TaskCreate,
    TaskRecord,
    TaskResponse,
    TaskUpdate,
)
from gitIssueAssitant.core.utils.git import git_status_short, is_git_repo
from gitIssueAssitant.core.utils.time import now_local


class TaskService:
    @staticmethod
    def _meaningful_status_files(status_output: str) -> list[str]:
        junk_patterns = (
            "__pycache__/",
            "/__pycache__/",
            ".pytest_cache/",
            ".mypy_cache/",
            ".ruff_cache/",
            ".tox/",
            "node_modules/",
        )
        file_paths: list[str] = []
        for line in status_output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            file_paths.append(parts[1].strip())
        return [
            file_path
            for file_path in file_paths
            if file_path
            and not any(pattern in file_path for pattern in junk_patterns)
            and not file_path.endswith((".pyc", ".pyo"))
        ]

    def _has_unpublished_changes(self, task: TaskRecord) -> bool:
        if task.status != "completed":
            return False
        repo_path = (
            task.repo_path
            or (task.result.current_state.repo_path if task.result and task.result.current_state else None)
        )
        if not repo_path:
            return False
        try:
            repo = Path(repo_path).expanduser().resolve()
            if not repo.exists() or not is_git_repo(repo):
                return False
            return bool(self._meaningful_status_files(git_status_short(repo)))
        except Exception:
            return False

    def _to_response(self, task: TaskRecord) -> TaskResponse:
        return TaskResponse(
            id=task.id,
            name=task.name,
            description=task.description,
            status=task.status,
            config=task.config,
            created_at=task.created_at,
            updated_at=task.updated_at,
            result=task.result,
            has_unpublished_changes=self._has_unpublished_changes(task),
        )

    def get_task_record(self, task_id: str) -> TaskRecord | None:
        return task_repository.get(task_id)

    def save_task_record(self, task: TaskRecord) -> TaskRecord:
        return task_repository.save(task)

    def list_task_records(self) -> list[TaskRecord]:
        return task_repository.list()

    def list_tasks(self) -> list[TaskResponse]:
        return [self._to_response(task) for task in task_repository.list()]

    def get_task(self, task_id: str) -> TaskResponse | None:
        task = task_repository.get(task_id)
        return self._to_response(task) if task else None

    def create_task(self, payload: TaskCreate) -> TaskResponse:
        now = now_local()
        task = TaskRecord(
            id=f"eval-{uuid4().hex[:8]}",
            name=payload.name,
            description=payload.description,
            status="draft",
            config=payload.config,
            created_at=now,
            updated_at=now,
        )
        return self._to_response(task_repository.save(task))

    def update_task(
        self, task_id: str, payload: TaskUpdate
    ) -> TaskResponse | None:
        task = task_repository.get(task_id)
        if task is None:
            return None

        if payload.name is not None:
            task.name = payload.name
        if payload.description is not None:
            task.description = payload.description
        if payload.status is not None:
            task.status = payload.status
        if payload.config is not None:
            task.config = payload.config
            task.result = None
            task.thread_id = None
            task.repo_path = None
            task.started_at = None
            task.finished_at = None

        return self._to_response(task_repository.save(task))

    def delete_task(self, task_id: str) -> bool:
        return task_repository.delete(task_id)


task_service = TaskService()


