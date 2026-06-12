from fastapi import APIRouter, HTTPException, Query

from gitIssueAssitant.core.schemas.memory import (
    LongTermMemoryListResponse,
    LongTermMemoryRebuildRequest,
    LongTermMemoryRebuildResponse,
)
from gitIssueAssitant.core.services.long_term_memory_service import long_term_memory_service


router = APIRouter()


@router.get("/", response_model=LongTermMemoryListResponse)
def list_memories(limit: int = Query(default=50, ge=1, le=100)) -> LongTermMemoryListResponse:
    return LongTermMemoryListResponse(items=long_term_memory_service.list_memories(limit))


@router.post("/rebuild", response_model=LongTermMemoryRebuildResponse)
async def rebuild_memories(payload: LongTermMemoryRebuildRequest | None = None) -> LongTermMemoryRebuildResponse:
    request = payload or LongTermMemoryRebuildRequest()
    items, skipped_count = await long_term_memory_service.rebuild_from_recent_tasks(request.limit)
    return LongTermMemoryRebuildResponse(
        count=len(items),
        skipped_count=skipped_count,
        items=items,
    )


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: str) -> None:
    if not long_term_memory_service.delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")


@router.delete("/", response_model=dict[str, int])
def clear_memories() -> dict[str, int]:
    return {"count": long_term_memory_service.clear_memories()}
