"""Repository package."""

__all__ = [
    "SessionStateRecord",
    "SessionStateRepository",
    "TaskRepository",
    "default_session_state_db_path",
    "task_repository",
]


def __getattr__(name: str):
    if name in {
        "SessionStateRecord",
        "SessionStateRepository",
        "default_session_state_db_path",
    }:
        from .session_state_repository import (
            SessionStateRecord,
            SessionStateRepository,
            default_session_state_db_path,
        )

        return {
            "SessionStateRecord": SessionStateRecord,
            "SessionStateRepository": SessionStateRepository,
            "default_session_state_db_path": default_session_state_db_path,
        }[name]
    if name in {"TaskRepository", "task_repository"}:
        from .task_repository import TaskRepository, task_repository

        return {
            "TaskRepository": TaskRepository,
            "task_repository": task_repository,
        }[name]
    raise AttributeError(name)
