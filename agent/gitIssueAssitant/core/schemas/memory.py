from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LongTermMemoryRecord(BaseModel):
    id: str
    task_id: str
    task_name: str
    repo_source: str
    issue_input: str
    outcome: str
    content: str
    tags: list[str] = Field(default_factory=list)
    source: str = "rule"
    created_at: datetime
    updated_at: datetime


class LongTermMemoryListResponse(BaseModel):
    items: list[LongTermMemoryRecord] = Field(default_factory=list)


class LongTermMemoryRebuildRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


class LongTermMemoryRebuildResponse(BaseModel):
    count: int
    skipped_count: int = 0
    items: list[LongTermMemoryRecord] = Field(default_factory=list)
