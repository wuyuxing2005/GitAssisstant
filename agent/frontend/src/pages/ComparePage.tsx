import { useMemo, useState } from "react";
import { analyticsReportUrl } from "../services/api";
import type { ComparisonResponse, EvaluationTask } from "../types/task";

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

export function ComparePage({ tasks, comparison }: ComparePageProps) {
  const [selectedCompareTaskIds, setSelectedCompareTaskIds] = useState<string[]>([]);

  const comparisonByTaskId = useMemo(() => {
    return new Map(comparison?.items.map((item) => [item.task_id, item]) ?? []);
  }, [comparison]);

  const taskById = useMemo(() => {
    return new Map(tasks.map((task) => [task.id, task]));
  }, [tasks]);

  const orderedTasks = useMemo(() => {
    if (!selectedCompareTaskIds.length) {
      return tasks;
    }
    return [...tasks].sort((first, second) => {
      const firstIndex = selectedCompareTaskIds.indexOf(first.id);
      const secondIndex = selectedCompareTaskIds.indexOf(second.id);
      if (firstIndex === -1 && secondIndex === -1) {
        return 0;
      }
      if (firstIndex === -1) {
        return 1;
      }
      if (secondIndex === -1) {
        return -1;
      }
      return firstIndex - secondIndex;
    });
  }, [selectedCompareTaskIds, tasks]);

  const firstSelectedId = selectedCompareTaskIds[0] ?? null;
  const secondSelectedId = selectedCompareTaskIds[1] ?? null;

  function handleTaskSelect(taskId: string) {
    setSelectedCompareTaskIds((current) => {
      if (current.includes(taskId)) {
        return current;
      }
      return [...current, taskId].slice(0, 2);
    });
  }

  function handleResetSelection() {
    setSelectedCompareTaskIds([]);
  }

  function renderComparisonDetail(item: ComparisonResponse["items"][number], label: string) {
    return (
      <article className="comparison-detail-card">
        <div className="comparison-card-header">
          <div>
            <span className="compare-side-label">{label}</span>
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
    );
  }

  function renderTaskDetail(taskId: string, label: string) {
    const comparisonItem = comparisonByTaskId.get(taskId);
    if (comparisonItem) {
      return renderComparisonDetail(comparisonItem, label);
    }

    const task = taskById.get(taskId);
    if (!task) {
      return null;
    }

    return (
      <article className="comparison-detail-card">
        <div className="comparison-card-header">
          <div>
            <span className="compare-side-label">{label}</span>
            <strong>{task.name}</strong>
            <p>{task.description || "该任务暂无描述。"}</p>
          </div>
          <span className={`status-badge ${task.status}`}>{statusText(task.status)}</span>
        </div>
        <div className="empty-state inline">
          <strong>暂无指标</strong>
          <p>该任务还没有可用于对比的运行结果。</p>
        </div>
      </article>
    );
  }

  return (
    <section className="card comparison-panel">
      <div className="section-header">
        <div>
          <h2>任务对比</h2>
          <p>横向比较不同任务的成功情况、迭代轮数、工具使用和测试验证情况。</p>
        </div>
        <div className="action-row">
          {selectedCompareTaskIds.length ? (
            <button className="secondary-button" type="button" onClick={handleResetSelection}>
              重新选择
            </button>
          ) : null}
          <a className="secondary-button" href={analyticsReportUrl("md", selectedCompareTaskIds)}>
            导出 Markdown
          </a>
          <a className="secondary-button" href={analyticsReportUrl("csv", selectedCompareTaskIds)}>
            导出 CSV
          </a>
        </div>
      </div>

      {tasks.length > 0 ? (
        <div className="compare-workspace">
          <div className="compare-pane">
            {secondSelectedId ? (
              renderTaskDetail(secondSelectedId, "")
            ) : (
              <div className="compare-task-list">
                <div>
                  <strong>请选择对比任务</strong>
                  <p className="muted-copy">
                    {firstSelectedId ? "选择对比任务。" : "查看任务详情。"}
                  </p>
                </div>
                <div className="compare-task-stack">
                  {orderedTasks.map((task) => {
                    const selected = selectedCompareTaskIds.includes(task.id);
                    return (
                      <button
                        key={task.id}
                        className={`compare-task-option${selected ? " selected" : ""}`}
                        type="button"
                        onClick={() => handleTaskSelect(task.id)}
                      >
                        <span className="compare-checkmark">{selected ? "✓" : ""}</span>
                        <span>
                          <strong>{task.name}</strong>
                          <small>{statusText(task.status)}</small>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          <div className="compare-pane">
            {firstSelectedId ? (
              renderTaskDetail(firstSelectedId, "")
            ) : (
              <div className="compare-empty-hint">
                <strong>等待选择</strong>
                <p>选择一个任务后，这里会展示它的详细指标。</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="empty-state comparison-empty-state">
          <strong>暂无任务</strong>
          <p>先创建任务，再进入这里选择对比对象。</p>
        </div>
      )}
    </section>
  );
}
