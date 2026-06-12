from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from gitIssueAssitant.core.schemas.memory import LongTermMemoryRecord
from gitIssueAssitant.core.utils.time import now_local


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _default_db_path() -> Path:
    configured = os.getenv("GIT_ISSUE_ASSISTANT_DB", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else (WORKSPACE_ROOT / path).resolve()
    return (WORKSPACE_ROOT / ".agent_data" / "conversations.sqlite3").resolve()


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not value:
        return now_local()
    return datetime.fromisoformat(str(value))


class LongTermMemoryRepository:
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
                CREATE TABLE IF NOT EXISTS long_term_memories (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL UNIQUE,
                    task_name TEXT NOT NULL,
                    repo_source TEXT NOT NULL,
                    issue_input TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'rule',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_long_term_memories_updated_at
                    ON long_term_memories(updated_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_long_term_memories_repo_source
                    ON long_term_memories(repo_source)
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(long_term_memories)").fetchall()
            }
            if "source" not in columns:
                conn.execute(
                    "ALTER TABLE long_term_memories ADD COLUMN source TEXT NOT NULL DEFAULT 'rule'"
                )

    def _row_to_record(self, row: sqlite3.Row) -> LongTermMemoryRecord:
        return LongTermMemoryRecord(
            id=row["id"],
            task_id=row["task_id"],
            task_name=row["task_name"],
            repo_source=row["repo_source"],
            issue_input=row["issue_input"],
            outcome=row["outcome"],
            content=row["content"],
            tags=json.loads(row["tags_json"] or "[]"),
            source=row["source"] or "rule",
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    def list(self, limit: int = 50) -> list[LongTermMemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM long_term_memories
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get(self, memory_id: str) -> LongTermMemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM long_term_memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def get_by_task_id(self, task_id: str) -> LongTermMemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM long_term_memories WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def save(self, memory: LongTermMemoryRecord) -> LongTermMemoryRecord:
        memory.updated_at = now_local()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO long_term_memories (
                    id, task_id, task_name, repo_source, issue_input,
                    outcome, content, tags_json, source, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    task_name=excluded.task_name,
                    repo_source=excluded.repo_source,
                    issue_input=excluded.issue_input,
                    outcome=excluded.outcome,
                    content=excluded.content,
                    tags_json=excluded.tags_json,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (
                    memory.id,
                    memory.task_id,
                    memory.task_name,
                    memory.repo_source,
                    memory.issue_input,
                    memory.outcome,
                    memory.content,
                    json.dumps(memory.tags, ensure_ascii=False),
                    memory.source,
                    memory.created_at.isoformat(),
                    memory.updated_at.isoformat(),
                ),
            )
        return memory

    def delete(self, memory_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM long_term_memories WHERE id = ?",
                (memory_id,),
            )
            return cursor.rowcount > 0

    def clear(self) -> int:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM long_term_memories")
            return cursor.rowcount


long_term_memory_repository = LongTermMemoryRepository()
