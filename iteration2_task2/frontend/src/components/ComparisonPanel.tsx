import { useState } from "react";

import type { ComparisonResponse, EvaluationTask } from "../types/task";
import { DimensionRadarChart, MetricBarChart } from "../components/charts";
import { labelDimension, labelMetric, labelStatus } from "../utils/labels";

interface ComparisonPanelProps {
  tasks: EvaluationTask[];
  selectedTaskIds: string[];
  comparison?: ComparisonResponse;
  onToggleTask: (taskId: string) => void;
}

export function ComparisonPanel({
  tasks,
  selectedTaskIds,
  comparison,
  onToggleTask,
}: ComparisonPanelProps) {
  const [viewMode, setViewMode] = useState<"cards" | "radar" | "bar">("cards");
  const selectedCount = selectedTaskIds.length;

  return (
    <section className="comparison-page">
      <section className="card">
        <div className="section-header">
          <div>
            <h2>选择对比任务</h2>
            <p>从当前任务列表中选择两个已完成任务，系统会自动生成横向对比。</p>
          </div>
          <div className="comparison-selection-summary">
            已选择 {selectedCount} / 2
          </div>
        </div>

        {tasks.length === 0 ? (
          <p className="empty-state">暂无任务。请先创建并运行评测任务。</p>
        ) : (
          <div className="compare-task-list">
            {tasks.map((task) => {
              const isSelected = selectedTaskIds.includes(task.id);
              const canSelect = task.status === "completed";
              const isLocked = !isSelected && selectedCount >= 2;
              const isDisabled = !isSelected && (!canSelect || isLocked);

              return (
                <button
                  key={task.id}
                  type="button"
                  className={`compare-task-option ${isSelected ? "selected" : ""}`}
                  onClick={() => (isSelected || (canSelect && !isLocked)) && onToggleTask(task.id)}
                  disabled={isDisabled}
                  title={!canSelect ? "只有已完成任务可以参与对比" : isLocked ? "最多选择两个任务" : undefined}
                >
                  <span className="compare-task-check">{isSelected ? "✓" : ""}</span>
                  <span className="compare-task-main">
                    <strong>{task.name}</strong>
                    <small>{task.config.dataset}</small>
                  </span>
                  <span className={`status-badge compact ${task.status}`}>
                    {labelStatus(task.status)}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="card">
      <div className="section-header">
        <div>
          <h2>对比分析</h2>
          <p>按评分卡和指标结果横向比较所选的两个评测任务。</p>
        </div>
        {comparison && comparison.items.length > 0 && (
          <div className="charts-tabs">
            <button
              type="button"
              className={`charts-tab ${viewMode === "cards" ? "active" : ""}`}
              onClick={() => setViewMode("cards")}
            >
              卡片
            </button>
            <button
              type="button"
              className={`charts-tab ${viewMode === "radar" ? "active" : ""}`}
              onClick={() => setViewMode("radar")}
            >
              雷达图
            </button>
            <button
              type="button"
              className={`charts-tab ${viewMode === "bar" ? "active" : ""}`}
              onClick={() => setViewMode("bar")}
            >
              柱状图
            </button>
          </div>
        )}
      </div>

      {selectedCount < 2 ? (
        <p className="empty-state">请先从上方任务列表中选择两个已完成任务。</p>
      ) : !comparison || comparison.items.length < 2 ? (
        <p className="empty-state">正在加载对比结果，或所选任务还没有可用评测结果。</p>
      ) : (
        <>
          {viewMode === "cards" && (
            <div className="comparison-grid">
              {comparison.items.map((item) => (
                <article key={item.task_id} className="comparison-card">
                  <h3>{item.task_name}</h3>
                  <p>{item.dataset}</p>
                  <div className="scorecard-row">
                    {Object.entries(item.scorecard).map(([key, value]) => (
                      <div key={key} className="mini-stat">
                        <span>{labelDimension(key)}</span>
                        <strong>{value}</strong>
                      </div>
                    ))}
                  </div>
                  <div className="comparison-metrics">
                    {item.scores.map((metric) => (
                      <div key={metric.key} className="metric-line">
                        <span>{labelMetric(metric.key, metric.label)}</span>
                        <strong>{metric.value} {metric.unit !== "score" ? metric.unit : ""}</strong>
                      </div>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          )}

          {viewMode === "radar" && (
            <div className="chart-card">
              <h4>维度对比</h4>
              {comparison.items.length >= 1 ? (
                <>
                  <DimensionRadarChart
                    metrics={comparison.items[0].scores}
                    compareTo={comparison.items[1]?.scores}
                    taskName={comparison.items[0].task_name}
                    compareTaskName={comparison.items[1].task_name}
                  />
                </>
              ) : (
                <p className="empty-state">暂无可用于雷达图的数据。</p>
              )}
            </div>
          )}

          {viewMode === "bar" && (
            <div className="chart-card">
              <h4>指标拆解</h4>
              {comparison.items.length >= 1 ? (
                <>
                  <MetricBarChart
                    metrics={comparison.items[0].scores}
                    compareTo={comparison.items[1]?.scores}
                    taskName={comparison.items[0].task_name}
                    compareTaskName={comparison.items[1].task_name}
                    maxHeight={500}
                  />
                </>
              ) : (
                <p className="empty-state">暂无可用于柱状图的数据。</p>
              )}
            </div>
          )}
        </>
      )}
    </section>
    </section>
  );
}
