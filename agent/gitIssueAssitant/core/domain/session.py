from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Session:
    session_id: str
    thread_id: str
    repo_path: str
    issue_ref: Optional[str] = None
    issue_description: Optional[str] = None
    sandbox_error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
