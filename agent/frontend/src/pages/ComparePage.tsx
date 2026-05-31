import { useEffect, useState } from "react";
import { analyticsReportUrl } from "../services/api";
import type { BadCaseRecord, ComparisonResponse, EvaluationTask } from "../types/task";

interface ComparePageProps {
  tasks: EvaluationTask[];
  badCases: BadCaseRecord[];
  comparison: ComparisonResponse | null;
}

function formatMetricValue(value: number): string {
  if (Number.isInteger(value)) {
    return value.toString();
  }
  return value.toFixed(2);
}

function statusText(status: EvaluationTask["status"]): string {
  const mapping: Record<EvaluationTask["status"], string> = {
    draft: "草稿",
    scheduled: "排队中",
    running: "执行中",
    completed: "已完成",
    failed: "失败"
  };

  return mapping[status];
}

function scoreByName(item: ComparisonResponse["items"][number], name: string): number {
  return item.scores.find((score) => score.name === name)?.value ?? 0;
}

export function ComparePage({ tasks, badCases, comparison }: ComparePageProps) {
  const [selectedCompareTaskIds, setSelectedCompareTaskIds] = useState<string[]>([]);
  const [selectedCompareBadCaseIds, setSelectedCompareBadCaseIds] = useState<string[]>([]);

  useEffect(() => {
    setSelectedCompareTaskIds((current) => {
      const ids = tasks.map((task) => task.id);
      return current.length ? current.filter((id) => ids.includes(id)) : ids;
    });
  }, [tasks]);

  useEffect(() => {
    setSelectedCompareBadCaseIds((current) => {
      const ids = badCases.map((item) => item.id);
      return current.length ? current.filter((id) => ids.includes(id)) : ids;
    });
  }, [badCases]);

  const visibleComparisonItems = comparison?.items.filter((item) => selectedCompareTaskIds.includes(item.task_id)) ?? [];
  const visibleAggregate = visibleComparisonItems.length
    ? {
        success_rate:
          visibleComparisonItems.reduce((sum, item) => sum + scoreByName(item, "success"), 0) /
          visibleComparisonItems.length,
        failed_count: visibleComparisonItems.filter((item) => item.status === "failed").length,
        average_duration_seconds:
          visibleComparisonItems.reduce((sum, item) => sum + scoreByName(item, "duration_seconds"), 0) /
          visibleComparisonItems.length,
        average_tool_call_count:
          visibleComparisonItems.reduce((sum, item) => sum + scoreByName(item, "tool_call_count"), 0) /
          visibleComparisonItems.length,
        average_test_run_count:
          visibleComparisonItems.reduce((sum, item) => sum + scoreByName(item, "test_run_count"), 0) /
          visibleComparisonItems.length
      }
    : comparison?.aggregate ?? {
        success_rate: 0,
        failed_count: 0,
        average_duration_seconds: 0,
        average_tool_call_count: 0,
        average_test_run_count: 0
      };

  return (
    <section className="card comparison-panel">
      <div className="section-header">
        <div>
          <h2>任务对比</h2>
          <p>横向比较不同任务的成功情况、迭代轮数、工具使用和测试验证情况。</p>
        </div>
        <div className="action-row">
          <a className="secondary-button" href={analyticsReportUrl("md", selectedCompareTaskIds, selectedCompareBadCaseIds)}>
            导出 Markdown
          </a>
          <a className="secondary-button" href={analyticsReportUrl("csv", selectedCompareTaskIds, selectedCompareBadCaseIds)}>
            导出 CSV
          </a>
        </div>
      </div>

      {comparison && comparison.items.length > 0 ? (
        <>
          <div className="aggregate-grid">
            <article>
              <span>成功率</span>
              <strong>{Math.round(visibleAggregate.success_rate * 100)}%</strong>
            </article>
            <article>
              <span>失败数</span>
              <strong>{visibleAggregate.failed_count}</strong>
            </article>
            <article>
              <span>平均耗时</span>
              <strong>{formatMetricValue(visibleAggregate.average_duration_seconds)} 秒</strong>
            </article>
            <article>
              <span>平均工具调用</span>
              <strong>{formatMetricValue(visibleAggregate.average_tool_call_count)}</strong>
            </article>
            <article>
              <span>平均测试次数</span>
              <strong>{formatMetricValue(visibleAggregate.average_test_run_count)}</strong>
            </article>
          </div>

          <div className="compare-selector">
            <strong>任务选择</strong>
            <div className="tag-grid">
              {tasks.map((task) => (
                <label key={task.id} className="checkbox-row tag-choice">
                  <input
                    type="checkbox"
                    checked={selectedCompareTaskIds.includes(task.id)}
                    onChange={(event) =>
                      setSelectedCompareTaskIds((current) =>
                        event.target.checked
                          ? Array.from(new Set([...current, task.id]))
                          : current.filter((id) => id !== task.id)
                      )
                    }
                  />
                  <span>{task.name}</span>
                </label>
              ))}
            </div>

            <strong>Bad Case 选择</strong>
            <div className="tag-grid">
              {badCases.map((item) => (
                <label key={item.id} className="checkbox-row tag-choice">
                  <input
                    type="checkbox"
                    checked={selectedCompareBadCaseIds.includes(item.id)}
                    onChange={(event) =>
                      setSelectedCompareBadCaseIds((current) =>
                        event.target.checked
                          ? Array.from(new Set([...current, item.id]))
                          : current.filter((id) => id !== item.id)
                      )
                    }
                  />
                  <span>{item.task_name}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="comparison-grid">
            {visibleComparisonItems.map((item) => (
              <article key={item.task_id} className="comparison-card">
                <div className="comparison-card-header">
                  <div>
                    <strong>{item.task_name}</strong>
                    <p>{item.summary}</p>
                  </div>
                  <span className={`status-badge ${item.status}`}>{statusText(item.status)}</span>
                </div>

                <div className="metric-list">
                  {item.scores.map((score) => (
                    <div key={`${item.task_id}-${score.name}`} className="metric-row">
                      <span>{score.name}</span>
                      <strong>
                        {formatMetricValue(score.value)}
                        {score.unit ? ` ${score.unit}` : ""}
                      </strong>
                    </div>
                  ))}
                </div>
              </article>
            ))}
            {!visibleComparisonItems.length ? (
              <div className="empty-state inline">
                <strong>未选择任务</strong>
                <p>在上方任务选择中勾选至少一个任务。</p>
              </div>
            ) : null}
          </div>
        </>
      ) : (
        <div className="empty-state">
          <strong>暂无可对比数据</strong>
          <p>先运行至少一个任务，再查看汇总指标矩阵。</p>
        </div>
      )}
    </section>
  );
}
