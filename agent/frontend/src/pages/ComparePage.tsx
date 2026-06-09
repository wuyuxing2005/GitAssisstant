import { useMemo, useState } from "react";
import { analyticsReportUrl } from "../services/api";
import type { ComparisonItem, ComparisonResponse, EvaluationTask, MetricScore } from "../types/task";
import { formatTaskStatus, getEffectiveTaskStatus } from "../utils/taskStatus";

interface ComparePageProps {
  tasks: EvaluationTask[];
  comparison: ComparisonResponse | null;
}

function formatMetricValue(value: number): string {
  if (Number.isInteger(value)) {
    return value.toString();
  }
  return value.toFixed(2);
}

function taskIssueDescription(task: EvaluationTask): string {
  return task.config.issue_input || task.description || "该任务暂无 Issue 描述。";
}

function metricDisplayValue(score: MetricScore | undefined): string {
  if (!score) {
    return "-";
  }
  return `${formatMetricValue(score.value)}${score.unit ? ` ${score.unit}` : ""}`;
}

function comparisonItemFromTask(task: EvaluationTask): ComparisonItem {
  const effectiveStatus = getEffectiveTaskStatus(task);
  return {
    task_id: task.id,
    task_name: task.name,
    status: effectiveStatus,
    summary: task.result?.summary || task.description || "该任务暂无对比摘要。",
    scores: task.result?.metrics ?? []
  };
}

export function ComparePage({ tasks, comparison }: ComparePageProps) {
  const [selectedCompareTaskIds, setSelectedCompareTaskIds] = useState<string[]>([]);
  const [comparisonModalOpen, setComparisonModalOpen] = useState(false);

  const comparisonByTaskId = useMemo(() => {
    return new Map(comparison?.items.map((item) => [item.task_id, item]) ?? []);
  }, [comparison]);

  const taskById = useMemo(() => {
    return new Map(tasks.map((task) => [task.id, task]));
  }, [tasks]);

  const selectedTasks = useMemo(() => {
    return selectedCompareTaskIds
      .map((taskId) => taskById.get(taskId))
      .filter((task): task is EvaluationTask => Boolean(task));
  }, [selectedCompareTaskIds, taskById]);

  const selectedComparisonItems = useMemo(() => {
    return selectedTasks.map((task) => comparisonByTaskId.get(task.id) ?? comparisonItemFromTask(task));
  }, [comparisonByTaskId, selectedTasks]);

  const metricNames = useMemo(() => {
    const names = new Set<string>(comparison?.compared_metrics ?? []);
    selectedComparisonItems.forEach((item) => {
      item.scores.forEach((score) => names.add(score.name));
    });
    return Array.from(names);
  }, [comparison?.compared_metrics, selectedComparisonItems]);

  function handleTaskSelect(taskId: string) {
    setSelectedCompareTaskIds((current) => {
      if (current.includes(taskId)) {
        return current.filter((selectedId) => selectedId !== taskId);
      }
      if (current.length >= 2) {
        return [current[1], taskId];
      }
      return [...current, taskId];
    });
  }

  return (
    <section className="card comparison-panel">
      <div className="section-header">
        <div>
          <h2>任务对比</h2>
          <p>选择两个任务后查看指标差异，横向比较成功情况、迭代轮数、工具使用和测试验证情况。</p>
        </div>
        <div className="action-row">
          {selectedCompareTaskIds.length === 2 ? (
            <button className="primary-button" type="button" onClick={() => setComparisonModalOpen(true)}>
              确定
            </button>
          ) : null}
        </div>
      </div>

      {tasks.length > 0 ? (
        <div className="compare-task-stack compare-task-stack-main">
          {tasks.map((task) => {
            const selected = selectedCompareTaskIds.includes(task.id);
            return (
              <button
                key={task.id}
                className={`compare-task-option compare-task-card${selected ? " selected" : ""}`}
                type="button"
                onClick={() => handleTaskSelect(task.id)}
                aria-pressed={selected}
              >
                <span className="compare-checkmark">{selected ? "✓" : ""}</span>
                <span className="compare-task-card-body">
                  <span className="compare-task-card-title">
                    <strong>{task.name}</strong>
                    <span className={`status-badge ${getEffectiveTaskStatus(task)}`}>{formatTaskStatus(getEffectiveTaskStatus(task))}</span>
                  </span>
                  <small title={taskIssueDescription(task)}>{taskIssueDescription(task)}</small>
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="empty-state comparison-empty-state">
          <strong>暂无任务</strong>
          <p>先创建任务，再进入这里选择对比对象。</p>
        </div>
      )}

      {comparisonModalOpen ? (
        <div className="modal-backdrop skill-modal-backdrop" role="presentation" onMouseDown={() => setComparisonModalOpen(false)}>
          <section
            className="settings-modal skill-create-modal comparison-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="comparison-modal-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="settings-modal-header">
              <div>
                <h2 id="comparison-modal-title">任务指标对比</h2>
                <p></p>
              </div>
              <div className="comparison-modal-actions">
                <details className="comparison-export-menu">
                  <summary>导出</summary>
                  <div>
                    <a href={analyticsReportUrl("csv", selectedCompareTaskIds)}>CSV</a>
                    <a href={analyticsReportUrl("md", selectedCompareTaskIds)}>Markdown</a>
                  </div>
                </details>
                <button className="modal-close-button" type="button" onClick={() => setComparisonModalOpen(false)} aria-label="关闭任务对比弹窗">
                  ×
                </button>
              </div>
            </div>

            <div className="comparison-modal-body">
              <table className="comparison-metric-table">
                <thead>
                  <tr>
                    <th></th>
                    {selectedComparisonItems.map((item) => (
                      <th key={item.task_id}>{item.task_name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>状态</td>
                    {selectedComparisonItems.map((item) => (
                      <td key={`${item.task_id}-status`}>
                        <span className={`status-badge ${item.status}`}>{formatTaskStatus(item.status)}</span>
                      </td>
                    ))}
                  </tr>

                  {metricNames.map((metricName) => (
                    <tr key={metricName}>
                      <td>{metricName}</td>
                      {selectedComparisonItems.map((item) => (
                        <td key={`${item.task_id}-${metricName}`}>
                          {metricDisplayValue(item.scores.find((score) => score.name === metricName))}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>

              {!metricNames.length ? (
                <div className="empty-state inline">
                  <strong>暂无指标</strong>
                  <p>所选任务还没有可用于对比的运行结果。</p>
                </div>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
