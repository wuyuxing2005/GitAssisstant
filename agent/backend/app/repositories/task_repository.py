from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.task import EvaluationTaskRecord
from app.schemas.task import EvaluationConfig, EvaluationResult
from app.utils.time import now_local


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _default_db_path() -> Path:
    configured = os.getenv("GIT_ISSUE_ASSISTANT_DB", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else (WORKSPACE_ROOT / path).resolve()
    return (WORKSPACE_ROOT / ".agent_data" / "conversations.sqlite3").resolve()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    return datetime.fromisoformat(str(value))


class TaskRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or _default_db_path()).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluation_tasks (
                    id TEXT PRIMARY KEY,
                    task_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_evaluation_tasks_updated_at
                    ON evaluation_tasks(updated_at)
                """
            )

    def _serialize_task(self, task: EvaluationTaskRecord) -> str:
        payload = asdict(task)
        payload["config"] = task.config.model_dump(mode="json")
        payload["result"] = task.result.model_dump(mode="json") if task.result else None
        for key in ("created_at", "updated_at", "started_at", "finished_at"):
            value = payload.get(key)
            payload[key] = value.isoformat() if isinstance(value, datetime) else value
        return json.dumps(payload, ensure_ascii=False)

    def _deserialize_task(self, payload: str) -> EvaluationTaskRecord:
        data = json.loads(payload)
        status = data["status"]
        if status == "running":
            status = "scheduled"
        return EvaluationTaskRecord(
            id=data["id"],
            name=data["name"],
            description=data.get("description") or "",
            status=status,
            config=EvaluationConfig.model_validate(data["config"]),
            created_at=_parse_datetime(data.get("created_at")) or now_local(),
            updated_at=_parse_datetime(data.get("updated_at")) or now_local(),
            result=EvaluationResult.model_validate(data["result"]) if data.get("result") else None,
            thread_id=data.get("thread_id"),
            repo_path=data.get("repo_path"),
            started_at=_parse_datetime(data.get("started_at")),
            finished_at=_parse_datetime(data.get("finished_at")),
        )

    def list(self) -> list[EvaluationTaskRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_json FROM evaluation_tasks ORDER BY updated_at DESC"
            ).fetchall()
        return [self._deserialize_task(row["task_json"]) for row in rows]

    def get(self, task_id: str) -> EvaluationTaskRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT task_json FROM evaluation_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return self._deserialize_task(row["task_json"]) if row else None

    def save(self, task: EvaluationTaskRecord) -> EvaluationTaskRecord:
        task.updated_at = now_local()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evaluation_tasks (id, task_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    task_json=excluded.task_json,
                    updated_at=excluded.updated_at
                """,
                (task.id, self._serialize_task(task), task.updated_at.isoformat()),
            )
        return task

    def delete(self, task_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM evaluation_tasks WHERE id = ?",
                (task_id,),
            )
            return cursor.rowcount > 0


task_repository = TaskRepository()
