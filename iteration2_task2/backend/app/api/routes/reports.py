"""
评测报告导出 API
"""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import TaskORM as DbTask
from app.db.models import EvaluationResultORM as DbResult
from app.schemas.task import EvaluationResult, EvaluationTaskResponse
from app.services.report_service import report_service

router = APIRouter()


@router.get("/reports/{task_id}")
async def export_report(
    task_id: str,
    format: Literal["json", "md", "pdf"] = Query("json", description="导出格式"),
    db: Session = Depends(get_db),
):
    """
    导出评测报告

    Args:
        task_id: 任务 ID
        format: 导出格式 (json, md, pdf)
    """
    # 查询任务
    db_task = db.query(DbTask).filter(DbTask.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 获取评测结果
    db_result = db.query(DbResult).filter(DbResult.task_id == task_id).first()
    if not db_result or not db_result.payload:
        raise HTTPException(status_code=400, detail="Task result not available yet")

    # 转换为 schema 对象
    task = EvaluationTaskResponse(
        id=db_task.id,
        name=db_task.name,
        description=db_task.description,
        status=db_task.status,
        created_at=db_task.created_at,
        updated_at=db_task.updated_at,
        config=db_task.config,
    )

    # 从 payload 中获取结果数据
    payload = db_result.payload
    result = EvaluationResult(
        task_id=payload.get("task_id", task_id),
        task_name=task.name,
        summary=payload.get("summary", ""),
        status=db_task.status,
        scorecard=payload.get("scorecard", {}),
        metrics=payload.get("metrics", []),
        timeline=payload.get("timeline", []),
        charts=payload.get("charts", []),
        logs_preview=payload.get("logs_preview", []),
    )

    # 导出报告
    try:
        if format == "json":
            filepath = report_service.export_json(task, result)
            return FileResponse(
                filepath,
                media_type="application/json",
                filename=f"{task_id}_report.json",
            )
        elif format == "md":
            filepath = report_service.export_markdown(task, result)
            return FileResponse(
                filepath,
                media_type="text/markdown",
                filename=f"{task_id}_report.md",
            )
        elif format == "pdf":
            # PDF 导出需要额外的依赖（如 weasyprint 或 reportlab）
            # 这里返回一个提示
            raise HTTPException(
                status_code=501,
                detail="PDF export is not yet implemented. Please use JSON or Markdown format.",
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export report: {str(e)}")


@router.get("/reports/{task_id}/preview")
async def preview_report(
    task_id: str,
    format: Literal["json", "md"] = Query("json", description="预览格式"),
    db: Session = Depends(get_db),
):
    """
    预览评测报告（返回内容而非文件）
    """
    db_task = db.query(DbTask).filter(DbTask.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    task = EvaluationTaskResponse(
        id=db_task.id,
        name=db_task.name,
        description=db_task.description,
        status=db_task.status,
        created_at=db_task.created_at,
        updated_at=db_task.updated_at,
        config=db_task.config,
    )

    # 从数据库获取结果
    db_result = db.query(DbResult).filter(DbResult.task_id == task_id).first()
    if not db_result or not db_result.payload:
        raise HTTPException(status_code=400, detail="Task result not available yet")

    payload = db_result.payload
    result = EvaluationResult(
        task_id=payload.get("task_id", task_id),
        task_name=task.name,
        summary=payload.get("summary", ""),
        status=db_task.status,
        scorecard=payload.get("scorecard", {}),
        metrics=payload.get("metrics", []),
        timeline=payload.get("timeline", []),
        charts=payload.get("charts", []),
        logs_preview=payload.get("logs_preview", []),
    )

    if format == "json":
        report_data = report_service._build_report_data(task, result)
        return JSONResponse(report_data)
    elif format == "md":
        md_content = report_service._generate_markdown(task, result)
        return Response(content=md_content, media_type="text/plain")
