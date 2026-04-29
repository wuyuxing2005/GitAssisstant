"""
过程导向评测服务

基于 Agent Trace 分析工具调用准确性、推理质量等过程指标。
"""

from typing import Any

from app.models.trace import AgentTrace, TraceAnalysisResult, TraceEventType, ToolCallInfo
from app.schemas.task import EvaluationTaskResponse


class ProcessEvaluationService:
    """过程导向评测服务"""

    def evaluate_trace(
        self, trace: AgentTrace, reference_tool_calls: list[dict[str, Any]] | None = None
    ) -> TraceAnalysisResult:
        """
        分析单条 Trace，评估过程质量。

        Args:
            trace: Agent 执行 trace
            reference_tool_calls: 参考工具调用列表（如果有标准答案）

        Returns:
            TraceAnalysisResult: 分析结果
        """
        issues: list[str] = []

        # 提取工具调用
        tool_calls = [
            e.tool_call for e in trace.events if e.event_type == TraceEventType.TOOL_CALL
        ]

        # 计算工具调用准确率
        tool_accuracy = self._calculate_tool_accuracy(tool_calls, reference_tool_calls, issues)

        # 评估推理质量
        reasoning_quality = self._evaluate_reasoning_quality(trace, issues)

        # 评估流程完整性
        process_completeness = self._evaluate_process_completeness(trace, issues)

        return TraceAnalysisResult(
            sample_id=trace.sample_id,
            tool_accuracy=tool_accuracy,
            reasoning_quality=reasoning_quality,
            process_completeness=process_completeness,
            issues=issues,
        )

    def _calculate_tool_accuracy(
        self,
        tool_calls: list[ToolCallInfo],
        reference_tool_calls: list[dict[str, Any]] | None,
        issues: list[str],
    ) -> float:
        """计算工具调用准确率"""
        if not tool_calls:
            # 没有工具调用，如果有参考调用则得 0 分，否则得 1 分
            if reference_tool_calls and len(reference_tool_calls) > 0:
                issues.append("Expected tool calls but none were made")
                return 0.0
            return 1.0

        if not reference_tool_calls:
            # 没有参考答案，检查工具调用是否成功执行
            successful = sum(1 for tc in tool_calls if tc.status == "success")
            return successful / len(tool_calls) if tool_calls else 1.0

        # 比较实际调用与参考调用
        matched = 0
        for ref in reference_tool_calls:
            for actual in tool_calls:
                if actual.name == ref.get("name"):
                    # 检查参数匹配度
                    if self._args_match(actual.arguments, ref.get("arguments", {})):
                        matched += 1
                        break
                    else:
                        issues.append(f"Tool {actual.name} called with incorrect arguments")
                    break
            else:
                issues.append(f"Expected tool call {ref.get('name')} not found")

        return matched / len(reference_tool_calls) if reference_tool_calls else 1.0

    def _args_match(self, actual: dict[str, Any], expected: dict[str, Any]) -> bool:
        """检查参数是否匹配（支持模糊匹配）"""
        if not expected:
            return True
        for key, value in expected.items():
            if key not in actual:
                return False
            if isinstance(value, dict):
                if not self._args_match(actual[key], value):
                    return False
            elif actual[key] != value:
                return False
        return True

    def _evaluate_reasoning_quality(self, trace: AgentTrace, issues: list[str]) -> float:
        """
        评估推理质量。

        检查点：
        1. 是否有清晰的思考步骤
        2. 是否正确处理了错误
        3. 是否有不必要的重复调用
        """
        score = 1.0

        # 检查错误处理
        error_events = [e for e in trace.events if e.event_type == TraceEventType.ERROR]
        if error_events:
            # 有错误但有恢复
            if len(error_events) <= len(trace.events) * 0.1:
                score -= 0.1
            else:
                score -= 0.3
                issues.append(f"High error rate: {len(error_events)} errors in trace")

        # 检查不必要的重复
        tool_calls = [
            e.tool_call.name for e in trace.events if e.event_type == TraceEventType.TOOL_CALL
        ]
        if len(tool_calls) > 5:
            unique_calls = len(set(tool_calls))
            if unique_calls < len(tool_calls) * 0.5:
                score -= 0.2
                issues.append("Possible redundant tool calls detected")

        return max(0.0, score)

    def _evaluate_process_completeness(self, trace: AgentTrace, issues: list[str]) -> float:
        """
        评估流程完整性。

        检查点：
        1. 是否有明确的开始和结束
        2. 是否处理了所有必要步骤
        3. 是否有合理的工具调用顺序
        """
        score = 1.0

        # 检查是否有用户输入和最终响应
        if not trace.user_input:
            score -= 0.3
            issues.append("Missing user input")
        if not trace.final_response:
            score -= 0.3
            issues.append("Missing final response")

        # 检查事件序列合理性
        if not trace.events:
            score -= 0.4
            issues.append("No intermediate events in trace")

        return max(0.0, score)

    def evaluate_task_traces(
        self,
        task: EvaluationTaskResponse,
        traces: list[AgentTrace],
        reference_data: list[dict[str, Any]],
    ) -> dict[str, float]:
        """
        评估任务的所有 traces，返回聚合分数。

        Args:
            task: 评测任务配置
            traces: Agent traces 列表
            reference_data: 参考数据列表

        Returns:
            各维度平均分
        """
        results: list[TraceAnalysisResult] = []

        for i, trace in enumerate(traces):
            ref_tool_calls = None
            if i < len(reference_data) and "reference_tool_calls" in reference_data[i]:
                ref_tool_calls = reference_data[i]["reference_tool_calls"]

            result = self.evaluate_trace(trace, ref_tool_calls)
            results.append(result)

        if not results:
            return {"tool_accuracy": 0.0, "reasoning_quality": 0.0, "process_completeness": 0.0}

        return {
            "tool_accuracy": sum(r.tool_accuracy for r in results) / len(results),
            "reasoning_quality": sum(r.reasoning_quality for r in results) / len(results),
            "process_completeness": sum(r.process_completeness for r in results) / len(results),
        }


process_evaluation_service = ProcessEvaluationService()
