"""
评测报告导出服务
支持 JSON、Markdown 和 PDF 格式
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from app.schemas.task import EvaluationResult, EvaluationTaskResponse


class ReportService:
    """评测报告生成服务"""

    def __init__(self, export_dir: str = "exports"):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_json(
        self,
        task: EvaluationTaskResponse,
        result: EvaluationResult,
        filename: str | None = None
    ) -> str:
        """导出 JSON 格式报告"""
        if filename is None:
            filename = f"{task.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        report_data = self._build_report_data(task, result)
        output_path = self.export_dir / filename

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        return str(output_path)

    def export_markdown(
        self,
        task: EvaluationTaskResponse,
        result: EvaluationResult,
        filename: str | None = None
    ) -> str:
        """导出 Markdown 格式报告"""
        if filename is None:
            filename = f"{task.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        md_content = self._generate_markdown(task, result)
        output_path = self.export_dir / filename

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        return str(output_path)

    def _build_report_data(
        self,
        task: EvaluationTaskResponse,
        result: EvaluationResult
    ) -> dict[str, Any]:
        """构建报告数据结构"""
        return {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "report_version": "1.0",
            },
            "task_info": {
                "id": task.id,
                "name": task.name,
                "description": task.description,
                "status": result.status,
                "created_at": task.created_at.isoformat() if hasattr(task.created_at, "isoformat") else str(task.created_at),
                "completed_at": datetime.now().isoformat(),
            },
            "evaluation_config": {
                "agent_version": task.config.agent_version,
                "dataset": task.config.dataset,
                "evaluation_modes": task.config.evaluation_modes,
                "evaluation_methods": task.config.evaluation_methods,
                "dimensions": task.config.dimensions,
                "builtin_metrics": task.config.builtin_metrics,
                "custom_metrics": [
                    {
                        "key": m.key,
                        "label": m.label,
                        "description": m.description,
                        "dimension": m.dimension,
                        "method": m.method,
                    }
                    for m in task.config.custom_metrics
                ],
                "strategy": {
                    "key": task.config.strategy.key,
                    "label": task.config.strategy.label,
                    "description": task.config.strategy.description,
                },
            },
            "evaluation_result": {
                "summary": result.summary,
                "scorecard": result.scorecard,
                "metrics": [
                    {
                        "key": m.key,
                        "label": m.label,
                        "value": m.value,
                        "unit": m.unit,
                        "category": m.category,
                        "method": m.method,
                        "source": m.source,
                        "description": m.description,
                    }
                    for m in result.metrics
                ],
                "timeline": [
                    {
                        "stage": e.stage,
                        "status": e.status,
                        "message": e.message,
                    }
                    for e in result.timeline
                ],
            },
            "dimension_analysis": self._analyze_dimensions(result),
        }

    def _analyze_dimensions(self, result: EvaluationResult) -> dict[str, Any]:
        """分析维度得分"""
        dimensions: dict[str, list[float]] = {
            "quality": [],
            "safety": [],
            "performance": [],
        }

        for metric in result.metrics:
            if metric.category in dimensions:
                dimensions[metric.category].append(metric.value)

        analysis = {}
        for dim, scores in dimensions.items():
            if scores:
                analysis[dim] = {
                    "average": sum(scores) / len(scores),
                    "min": min(scores),
                    "max": max(scores),
                    "count": len(scores),
                }

        return analysis

    def _generate_markdown(
        self,
        task: EvaluationTaskResponse,
        result: EvaluationResult
    ) -> str:
        """生成 Markdown 报告内容"""
        lines = []

        # 标题
        lines.append(f"# 评测报告：{task.name}")
        lines.append("")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**任务 ID**: {task.id}")
        lines.append("")

        # 摘要
        lines.append("## 摘要")
        lines.append("")
        lines.append(result.summary)
        lines.append("")

        # 评分卡
        lines.append("## 评分卡")
        lines.append("")
        lines.append("| 维度 | 得分 |")
        lines.append("|------|------|")
        for dim, score in result.scorecard.items():
            lines.append(f"| {dim} | {score:.2f} |")
        lines.append("")

        # 维度分析
        dimension_analysis = self._analyze_dimensions(result)
        if dimension_analysis:
            lines.append("## 维度分析")
            lines.append("")
            for dim, stats in dimension_analysis.items():
                lines.append(f"### {dim.capitalize()}")
                lines.append(f"- 平均分：{stats['average']:.2f}")
                lines.append(f"- 最低分：{stats['min']:.2f}")
                lines.append(f"- 最高分：{stats['max']:.2f}")
                lines.append(f"- 指标数：{stats['count']}")
                lines.append("")

        # 详细指标
        lines.append("## 详细指标")
        lines.append("")
        lines.append("| 指标 | 标签 | 得分 | 单位 | 维度 | 方法 |")
        lines.append("|------|------|------|------|------|------|")
        for metric in result.metrics:
            lines.append(
                f"| {metric.key} | {metric.label} | {metric.value:.2f} | "
                f"{metric.unit} | {metric.category} | {metric.method} |"
            )
        lines.append("")

        # 时间线
        lines.append("## 执行时间线")
        lines.append("")
        for event in result.timeline:
            status_icon = {
                "pending": "⏳",
                "running": "▶️",
                "completed": "✅",
            }.get(event.status, "⚪")
            lines.append(f"- {status_icon} **{event.stage}**: {event.status} - {event.message}")
        lines.append("")

        # 配置信息
        lines.append("## 评测配置")
        lines.append("")
        lines.append(f"- **Agent 版本**: {task.config.agent_version}")
        lines.append(f"- **数据集**: {task.config.dataset}")
        lines.append(f"- **评估模式**: {' / '.join(task.config.evaluation_modes)}")
        lines.append(f"- **评估方法**: {' / '.join(task.config.evaluation_methods)}")
        lines.append(f"- **评估维度**: {' / '.join(task.config.dimensions)}")
        lines.append(f"- **内置指标**: {', '.join(task.config.builtin_metrics)}")
        if task.config.custom_metrics:
            custom_labels = [m.label for m in task.config.custom_metrics]
            lines.append(f"- **自定义指标**: {', '.join(custom_labels)}")
        lines.append(f"- **策略**: {task.config.strategy.label}")
        lines.append("")

        # 页脚
        lines.append("---")
        lines.append("*本报告由 Agent Evaluation Platform 自动生成*")

        return "\n".join(lines)


report_service = ReportService()
