from fastapi import APIRouter, Query, Response

from gitIssueAssitant.core.schemas.task import ComparisonResponse
from gitIssueAssitant.core.services.issue_assistant_service import issue_assistant_service

router = APIRouter()


@router.get("/compare", response_model=ComparisonResponse)
def compare_tasks(task_ids: list[str] = Query(default=[])) -> ComparisonResponse:
    return issue_assistant_service.compare_tasks(task_ids)


@router.get("/report.md")
def export_markdown_report(
    task_ids: list[str] = Query(default=[]),
) -> Response:
    markdown = issue_assistant_service.export_tasks_report_markdown(task_ids)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="agent-eval-report.md"'},
    )


@router.get("/report.csv")
def export_csv_report(
    task_ids: list[str] = Query(default=[]),
) -> Response:
    csv_content = issue_assistant_service.export_tasks_report_csv(task_ids)
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="agent-eval-report.csv"'},
    )


