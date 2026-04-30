"""
数据集管理 API

支持数据集上传、列表、删除等操作。
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional
import json
import shutil
from pathlib import Path

from app.db.database import get_db
from app.core.config import get_settings

router = APIRouter(tags=["datasets"])

settings = get_settings()


def get_dataset_dir() -> Path:
    """获取数据集存储目录"""
    dataset_dir = Path(settings.ragas_dataset_dir)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    return dataset_dir


def validate_jsonl_file(file_path: Path) -> tuple[bool, list[str]]:
    """
    验证 JSONL 文件格式

    返回：(是否有效，错误消息列表)
    """
    errors = []
    valid_lines = 0

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        errors.append(f"Line {line_num}: Expected JSON object, got {type(data).__name__}")
                    else:
                        # 检查必要字段
                        if "user_input" not in data:
                            errors.append(f"Line {line_num}: Missing required field 'user_input'")
                        valid_lines += 1
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {str(e)}")
    except Exception as e:
        errors.append(f"Failed to read file: {str(e)}")

    return len(errors) == 0, errors


@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    validate: Optional[bool] = True,
    db: Session = Depends(get_db)
) -> dict:
    """
    上传数据集文件

    支持 JSONL 格式，可选验证。
    """
    if not file.filename.endswith('.jsonl'):
        raise HTTPException(status_code=400, detail="Only JSONL files are supported")

    dataset_dir = get_dataset_dir()
    dataset_name = file.filename[:-6]  # 移除 .jsonl 后缀

    # 检查数据集名称是否合法
    if not dataset_name:
        raise HTTPException(status_code=400, detail="Invalid dataset name")

    # 保存文件
    file_path = dataset_dir / f"{dataset_name}.jsonl"

    try:
        content = await file.read()

        # 如果启用验证，先保存到临时文件进行验证
        if validate:
            temp_path = dataset_dir / f"_temp_{dataset_name}.jsonl"
            with open(temp_path, 'wb') as f:
                f.write(content)

            is_valid, errors = validate_jsonl_file(temp_path)

            if not is_valid:
                temp_path.unlink()  # 删除临时文件
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Dataset validation failed",
                        "errors": errors[:10]  # 最多返回 10 个错误
                    }
                )

            # 验证通过，移动文件
            shutil.move(str(temp_path), str(file_path))
        else:
            # 不验证，直接保存
            with open(file_path, 'wb') as f:
                f.write(content)

        # 统计行数
        line_count = sum(1 for line in open(file_path, 'r', encoding='utf-8') if line.strip())

        return {
            "message": "Dataset uploaded successfully",
            "dataset_name": dataset_name,
            "file_path": str(file_path),
            "line_count": line_count
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save dataset: {str(e)}")


@router.get("/")
def list_datasets(db: Session = Depends(get_db)) -> list[dict]:
    """
    获取所有可用数据集列表
    """
    dataset_dir = get_dataset_dir()
    datasets = []

    if dataset_dir.exists():
        for file in dataset_dir.glob("*.jsonl"):
            if file.name.startswith("_temp_"):
                continue

            try:
                line_count = sum(1 for line in open(file, 'r', encoding='utf-8') if line.strip())
                datasets.append({
                    "name": file.stem,
                    "file_name": file.name,
                    "line_count": line_count,
                    "size_bytes": file.stat().st_size,
                    "created_at": file.stat().st_ctime,
                    "modified_at": file.stat().st_mtime
                })
            except Exception as e:
                datasets.append({
                    "name": file.stem,
                    "file_name": file.name,
                    "error": str(e)
                })

    return datasets


@router.get("/{dataset_name}")
def get_dataset_info(
    dataset_name: str,
    limit: Optional[int] = 5,
    db: Session = Depends(get_db)
) -> dict:
    """
    获取数据集详细信息

    可指定预览行数。
    """
    dataset_dir = get_dataset_dir()
    file_path = dataset_dir / f"{dataset_name}.jsonl"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        # 读取前 N 行作为预览
        preview = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= limit:
                    break
                if line.strip():
                    preview.append(json.loads(line))

        stat = file_path.stat()

        return {
            "name": dataset_name,
            "file_name": file_path.name,
            "total_lines": sum(1 for _ in open(file_path, 'r', encoding='utf-8')),
            "size_bytes": stat.st_size,
            "created_at": stat.st_ctime,
            "modified_at": stat.st_mtime,
            "preview": preview
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read dataset: {str(e)}")


@router.delete("/{dataset_name}")
def delete_dataset(
    dataset_name: str,
    db: Session = Depends(get_db)
) -> dict:
    """
    删除数据集
    """
    dataset_dir = get_dataset_dir()
    file_path = dataset_dir / f"{dataset_name}.jsonl"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        file_path.unlink()
        return {
            "message": f"Dataset '{dataset_name}' deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete dataset: {str(e)}")
