import { useState } from "react";

import type { EvaluationResult, EvaluationTask } from "../types/task";
import { TraceViewer } from "../components/TraceViewer";
import { DimensionRadarChart, MetricBarChart, TimelineProgress } from "../components/charts";
import { downloadReport } from "../services/api";

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
            <h2>Single Task Analysis</h2>
            <p>Select a task from the table</p>
          </div>
        </div>
        <p className="empty-state">No task selected.</p>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>Single Task Analysis</h2>
          <p>{task.name}</p>
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
          <div className="charts-tabs">
            <button
              type="button"
              className={`charts-tab ${activeTab === "overview" ? "active" : ""}`}
              onClick={() => setActiveTab("overview")}
            >
              Overview
            </button>
            <button
              type="button"
              className={`charts-tab ${activeTab === "charts" ? "active" : ""}`}
              onClick={() => setActiveTab("charts")}
            >
              Charts
            </button>
            <button
              type="button"
              className={`charts-tab ${activeTab === "traces" ? "active" : ""}`}
              onClick={() => setActiveTab("traces")}
            >
              Traces
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
                Export
              </button>
            </div>
          )}
        </div>
      </div>

      {activeTab === "overview" && (
        <div className="overview-content">
          {/* Scorecard Section */}
          <div className="overview-section">
            <h3 className="section-title">Scorecard</h3>
            <div className="score-grid">
              {result && Object.entries(result.scorecard).length > 0 ? (
                Object.entries(result.scorecard).map(([key, value]) => (
                  <article key={key} className="score-card">
                    <span className="score-label">{key}</span>
                    <strong className="score-value">{value}</strong>
                  </article>
                ))
              ) : (
                <p className="empty-state">Run this task to generate scorecard.</p>
              )}
            </div>
          </div>

          {/* Task Configuration */}
          <div className="info-card">
            <h3 className="card-title">Task Configuration</h3>
            <dl className="config-list">
              <div className="config-row">
                <dt>Agent Version</dt>
                <dd>{task.config.agent_version}</dd>
              </div>
              <div className="config-row">
                <dt>Dataset</dt>
                <dd>{task.config.dataset}</dd>
              </div>
              <div className="config-row">
                <dt>Evaluation Modes</dt>
                <dd>{task.config.evaluation_modes.join(", ")}</dd>
              </div>
              <div className="config-row">
                <dt>Methods</dt>
                <dd>{task.config.evaluation_methods.join(", ")}</dd>
              </div>
              <div className="config-row">
                <dt>Dimensions</dt>
                <dd>{task.config.dimensions.join(", ")}</dd>
              </div>
              <div className="config-row">
                <dt>Strategy</dt>
                <dd>{task.config.strategy.label}</dd>
              </div>
            </dl>
          </div>

          {/* Run Summary */}
          <div className="info-card">
            <h3 className="card-title">Run Summary</h3>
            <p className="summary-text">{result?.summary ?? "Run this task to generate evaluation results."}</p>
            {result?.timeline && result.timeline.length > 0 && (
              <TimelineProgress timeline={result.timeline} />
            )}
          </div>

          {/* Metric Results */}
          <div className="info-card">
            <h3 className="card-title">Metric Results</h3>
            {result && result.metrics.length > 0 ? (
              <table className="metrics-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Value</th>
                    <th>Category</th>
                  </tr>
                </thead>
                <tbody>
                  {result.metrics.map((metric) => (
                    <tr key={metric.key}>
                      <td className="metric-name">{metric.label}</td>
                      <td className="metric-value">
                        {metric.value} {metric.unit !== "score" ? metric.unit : ""}
                      </td>
                      <td className="metric-category">
                        <span className={`category-badge ${metric.category}`}>{metric.category}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="empty-state">No metrics yet.</p>
            )}
          </div>

          {/* Execution Logs */}
          <div className="info-card">
            <h3 className="card-title">Execution Logs</h3>
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
              <p className="empty-state">No logs yet.</p>
            )}
          </div>
        </div>
      )}

      {activeTab === "charts" && (
        <div className="charts-panel">
          {result ? (
            <>
              <div className="chart-card">
                <h4>Dimension Radar Chart</h4>
                <DimensionRadarChart metrics={result.metrics} taskName={task.name} />
              </div>
              <div className="chart-card">
                <h4>Metric Breakdown</h4>
                <MetricBarChart metrics={result.metrics} maxHeight={500} />
              </div>
            </>
          ) : (
            <p className="empty-state">Run this task to generate charts.</p>
          )}
        </div>
      )}

      {activeTab === "traces" && (
        <div className="chart-card">
          <h4>Execution Traces</h4>
          <TraceViewer taskId={task.id} />
        </div>
      )}
    </section>
  );
}
