import { useState } from "react";

import type { EvaluationResult, EvaluationTask } from "../types/task";
import { TraceViewer } from "../components/TraceViewer";
import { DimensionRadarChart, MetricBarChart, TimelineProgress } from "../components/charts";
import { downloadReport } from "../services/api";
import { labelDimension, labelMethod, labelMetric, labelMode } from "../utils/labels";

interface TaskDetailPageProps {
  task?: EvaluationTask;
  result?: EvaluationResult;
}

export function TaskDetailPage({ task, result }: TaskDetailPageProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "charts" | "traces">("overview");
  const [exportFormat, setExportFormat] = useState<"json" | "md">("json");

  const handleExport = () => {
    if (task) {
      downloadReport(task.id, exportFormat);
    }
  };

  if (!task) {
    return (
      <section className="card">
        <div className="section-header">
          <div>
            <h2>单任务分析</h2>
            <p>请先从任务表中选择一个任务</p>
          </div>
        </div>
        <p className="empty-state">尚未选择任务。</p>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>单任务分析</h2>
          <p>{task.name}</p>
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
          <div className="charts-tabs">
            <button
              type="button"
              className={`charts-tab ${activeTab === "overview" ? "active" : ""}`}
              onClick={() => setActiveTab("overview")}
            >
              概览
            </button>
            <button
              type="button"
              className={`charts-tab ${activeTab === "charts" ? "active" : ""}`}
              onClick={() => setActiveTab("charts")}
            >
              图表
            </button>
            <button
              type="button"
              className={`charts-tab ${activeTab === "traces" ? "active" : ""}`}
              onClick={() => setActiveTab("traces")}
            >
              执行链路
            </button>
          </div>
          {result && (
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <select
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value as "json" | "md")}
                style={{ padding: "8px 12px", borderRadius: "8px", border: "1px solid rgba(18, 32, 51, 0.14)" }}
              >
                <option value="json">JSON</option>
                <option value="md">Markdown</option>
              </select>
              <button
                className="primary-button"
                onClick={handleExport}
                style={{ padding: "8px 16px" }}
              >
                导出
              </button>
            </div>
          )}
        </div>
      </div>

      {activeTab === "overview" && (
        <div className="overview-content">
          {/* Scorecard Section */}
          <div className="overview-section">
            <h3 className="section-title">评分卡</h3>
            <div className="score-grid">
              {result && Object.entries(result.scorecard).length > 0 ? (
                Object.entries(result.scorecard).map(([key, value]) => (
                  <article key={key} className="score-card">
                    <span className="score-label">{labelDimension(key)}</span>
                    <strong className="score-value">{value}</strong>
                  </article>
                ))
              ) : (
                <p className="empty-state">运行任务后生成评分卡。</p>
              )}
            </div>
          </div>

          {/* Task Configuration */}
          <div className="info-card">
            <h3 className="card-title">任务配置</h3>
            <dl className="config-list">
              <div className="config-row">
                <dt>数据集</dt>
                <dd>{task.config.dataset}</dd>
              </div>
              <div className="config-row">
                <dt>评测模式</dt>
                <dd>{task.config.evaluation_modes.map(labelMode).join("、")}</dd>
              </div>
              <div className="config-row">
                <dt>评测方法</dt>
                <dd>{task.config.evaluation_methods.map(labelMethod).join("、")}</dd>
              </div>
              <div className="config-row">
                <dt>评测维度</dt>
                <dd>{task.config.dimensions.map(labelDimension).join("、")}</dd>
              </div>
              <div className="config-row">
                <dt>组合策略</dt>
                <dd>{task.config.strategy.label}</dd>
              </div>
            </dl>
          </div>

          {/* Run Summary */}
          <div className="info-card">
            <h3 className="card-title">运行摘要</h3>
            <p className="summary-text">{result?.summary ?? "运行任务后生成评测结果。"}</p>
            {result?.timeline && result.timeline.length > 0 && (
              <TimelineProgress timeline={result.timeline} />
            )}
          </div>

          {/* Metric Results */}
          <div className="info-card">
            <h3 className="card-title">指标结果</h3>
            {result && result.metrics.length > 0 ? (
              <table className="metrics-table">
                <thead>
                  <tr>
                    <th>指标</th>
                    <th>得分</th>
                    <th>维度</th>
                  </tr>
                </thead>
                <tbody>
                  {result.metrics.map((metric) => (
                    <tr key={metric.key}>
                      <td className="metric-name">{labelMetric(metric.key, metric.label)}</td>
                      <td className="metric-value">
                        {metric.value} {metric.unit !== "score" ? metric.unit : ""}
                      </td>
                      <td className="metric-category">
                        <span className={`category-badge ${metric.category}`}>{labelDimension(metric.category)}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="empty-state">暂无指标结果。</p>
            )}
          </div>

          {/* Execution Logs */}
          <div className="info-card">
            <h3 className="card-title">执行日志</h3>
            {result && result.logs_preview && result.logs_preview.length > 0 ? (
              <div className="log-container">
                {result.logs_preview.map((line, index) => (
                  <div key={index} className="log-line">
                    <span className="log-index">{index + 1}</span>
                    <code className="log-content">{line}</code>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-state">暂无日志。</p>
            )}
          </div>
        </div>
      )}

      {activeTab === "charts" && (
        <div className="charts-panel">
          {result ? (
            <>
              <div className="chart-card">
                <h4>维度雷达图</h4>
                <DimensionRadarChart metrics={result.metrics} taskName={task.name} />
              </div>
              <div className="chart-card">
                <h4>指标拆解</h4>
                <MetricBarChart metrics={result.metrics} maxHeight={500} />
              </div>
            </>
          ) : (
            <p className="empty-state">运行任务后生成图表。</p>
          )}
        </div>
      )}

      {activeTab === "traces" && (
        <div className="chart-card">
          <h4>执行链路</h4>
          <TraceViewer taskId={task.id} />
        </div>
      )}
    </section>
  );
}
