from fastapi import APIRouter, Query, Response

from app.schemas.task import ComparisonResponse
from app.services.evaluation_service import evaluation_service

router = APIRouter()


@router.get("/compare", response_model=ComparisonResponse)
def compare_tasks(task_ids: list[str] = Query(default=[])) -> ComparisonResponse:
    return evaluation_service.compare(task_ids)


@router.get("/report.md")
def export_markdown_report(
    task_ids: list[str] = Query(default=[]),
    bad_case_ids: list[str] = Query(default=[]),
) -> Response:
    markdown = evaluation_service.export_report_markdown(task_ids, bad_case_ids)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="agent-eval-report.md"'},
    )


@router.get("/report.csv")
def export_csv_report(
    task_ids: list[str] = Query(default=[]),
    bad_case_ids: list[str] = Query(default=[]),
) -> Response:
    csv_content = evaluation_service.export_report_csv(task_ids, bad_case_ids)
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="agent-eval-report.csv"'},
    )
