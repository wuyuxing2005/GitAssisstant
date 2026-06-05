from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import messages_from_dict, messages_to_dict


def _now_iso() -> str:
    return datetime.now().isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return str(value)


class AgentConversationStore:
    """SQLite-backed persistence for agent sessions and LangGraph state snapshots."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL UNIQUE,
                    repo_path TEXT NOT NULL,
                    issue_ref TEXT,
                    issue_description TEXT,
                    sandbox_error TEXT,
                    max_iterations INTEGER NOT NULL DEFAULT 25,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_states (
                    thread_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    last_node TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
                    ON sessions(updated_at);
                """
            )
            try:
                conn.execute("ALTER TABLE agent_states ADD COLUMN last_node TEXT")
            except sqlite3.OperationalError:
                pass

    def save_session(self, session: Any) -> None:
        payload = asdict(session) if hasattr(session, "__dataclass_fields__") else dict(session)
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, thread_id, repo_path, issue_ref, issue_description,
                    sandbox_error, max_iterations, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    thread_id=excluded.thread_id,
                    repo_path=excluded.repo_path,
                    issue_ref=excluded.issue_ref,
                    issue_description=excluded.issue_description,
                    sandbox_error=excluded.sandbox_error,
                    max_iterations=excluded.max_iterations,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["session_id"],
                    payload["thread_id"],
                    payload["repo_path"],
                    payload.get("issue_ref"),
                    payload.get("issue_description"),
                    payload.get("sandbox_error"),
                    int(payload.get("max_iterations") or 25),
                    payload.get("created_at") or now,
                    now,
                ),
            )

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def save_state(
        self,
        session_id: str,
        thread_id: str,
        state: dict[str, Any],
        *,
        last_node: str | None = None,
    ) -> None:
        payload = self._serialize_state(state)
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_states (thread_id, session_id, state_json, last_node, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    state_json=excluded.state_json,
                    last_node=COALESCE(excluded.last_node, agent_states.last_node),
                    updated_at=excluded.updated_at
                """,
                (thread_id, session_id, payload, last_node, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )

    def load_state_record(self, thread_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json, last_node FROM agent_states WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "state": self._deserialize_state(row["state_json"]),
            "last_node": row["last_node"],
        }

    def load_state(self, thread_id: str) -> dict[str, Any] | None:
        record = self.load_state_record(thread_id)
        return record["state"] if record else None

    def _serialize_state(self, state: dict[str, Any]) -> str:
        serializable = dict(state)
        messages = serializable.get("messages")
        if messages is not None:
            serializable["messages"] = messages_to_dict(list(messages))
        return json.dumps(serializable, ensure_ascii=False, default=_json_default)

    def _deserialize_state(self, state_json: str) -> dict[str, Any]:
        state = json.loads(state_json)
        messages = state.get("messages")
        if isinstance(messages, list):
            state["messages"] = messages_from_dict(messages)
        return state


def default_store_path(workspace_root: str | Path) -> Path:
    configured = Path(
        str(Path.cwd() if workspace_root is None else workspace_root)
    )
    env_value = __import__("os").getenv("GIT_ISSUE_ASSISTANT_DB", "").strip()
    if env_value:
        path = Path(env_value).expanduser()
        return path if path.is_absolute() else (configured / path).resolve()
    return (configured / ".agent_data" / "conversations.sqlite3").resolve()
