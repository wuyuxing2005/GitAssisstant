"""
执行链路数据管理 API

支持 Agent 执行链路数据上传、查询和删除。
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional
import json

from app.db.database import get_db
from app.models.trace import AgentTrace
from app.services.trace_loader import trace_loader

router = APIRouter(tags=["traces"])


@router.post("/upload")
def upload_trace(
    trace_data: dict,
    db: Session = Depends(get_db)
) -> dict[str, str]:
    """
    上传单条 Agent 执行链路数据

    请求体格式：
    {
        "trace_id": "trace-001",
        "task_id": "task-123",
        "sample_id": "sample-001",
        "user_input": "用户输入",
        "final_response": "Agent 响应",
        "events": [...],
        "total_latency_ms": 1000.0,
        "token_usage": {"prompt": 100, "completion": 50, "total": 150}
    }
    """
    try:
        trace = AgentTrace(**trace_data)
        trace_loader.save_trace(trace)
        return {
            "message": "执行链路上传成功",
            "trace_id": trace.trace_id,
            "task_id": trace.task_id,
            "sample_id": trace.sample_id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存执行链路失败：{str(e)}") from e


@router.post("/upload/batch")
def upload_traces_batch(
    traces: list[dict],
    db: Session = Depends(get_db)
) -> dict:
    """
    批量上传 Agent 执行链路数据

    请求体格式：执行链路数组
    """
    success_count = 0
    failed_count = 0
    errors = []

    for i, trace_data in enumerate(traces):
        try:
            trace = AgentTrace(**trace_data)
            trace_loader.save_trace(trace)
            success_count += 1
        except Exception as e:
            failed_count += 1
            errors.append({"index": i, "error": str(e)})

    return {
        "message": f"批量上传完成：成功 {success_count} 条，失败 {failed_count} 条",
        "success_count": success_count,
        "failed_count": failed_count,
        "errors": errors if errors else None
    }


@router.post("/upload/file")
async def upload_trace_file(
    file: UploadFile = File(...),
    task_id: Optional[str] = None,
    db: Session = Depends(get_db)
) -> dict:
    """
    从文件上传执行链路数据

    支持 JSONL 或 JSON 格式
    """
    content = await file.read()

    try:
        # 尝试解析 JSONL 或 JSON
        if file.filename.endswith('.jsonl'):
            traces = []
            for line in content.decode('utf-8').splitlines():
                if line.strip():
                    traces.append(json.loads(line))
        else:
            data = json.loads(content.decode('utf-8'))
            traces = data if isinstance(data, list) else [data]

        # 如果指定了 task_id，更新所有执行链路的 task_id
        if task_id:
            for trace in traces:
                trace["task_id"] = task_id

        success_count = 0
        errors = []

        for i, trace_data in enumerate(traces):
            try:
                trace = AgentTrace(**trace_data)
                trace_loader.save_trace(trace)
                success_count += 1
            except Exception as e:
                errors.append({"index": i, "error": str(e)})

        return {
            "message": f"文件上传完成：已保存 {success_count} 条执行链路",
            "total_count": len(traces),
            "success_count": success_count,
            "errors": errors if errors else None
        }

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON 格式无效：{str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理文件失败：{str(e)}") from e


@router.get("/{task_id}")
def get_traces_by_task(
    task_id: str,
    db: Session = Depends(get_db)
) -> list[dict]:
    """
    获取指定任务的所有执行链路数据
    """
    traces = trace_loader.get_traces_by_task(task_id)
    if traces is None:
        traces = []
    return [trace.model_dump() for trace in traces]


@router.get("/{task_id}/{sample_id}")
def get_trace(
    task_id: str,
    sample_id: str,
    db: Session = Depends(get_db)
) -> dict:
    """
    获取单条执行链路数据
    """
    trace = trace_loader.get_trace(task_id, sample_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="执行链路不存在")
    return trace.model_dump()


@router.delete("/{task_id}")
def delete_traces(
    task_id: str,
    db: Session = Depends(get_db)
) -> dict[str, str]:
    """
    删除指定任务的所有执行链路数据
    """
    trace_loader.delete_traces(task_id)
    return {"message": f"任务 {task_id} 的执行链路已删除"}


@router.delete("/{task_id}/{sample_id}")
def delete_trace(
    task_id: str,
    sample_id: str,
    db: Session = Depends(get_db)
) -> dict[str, str]:
    """
    删除单条执行链路数据
    """
    trace_loader.delete_trace(task_id, sample_id)
    return {"message": f"任务 {task_id} 的执行链路 {sample_id} 已删除"}
