import { useState } from "react";

import type { ComparisonResponse } from "../types/task";
import { DimensionRadarChart, MetricBarChart } from "../components/charts";

interface ComparisonPanelProps {
  comparison?: ComparisonResponse;
}

export function ComparisonPanel({ comparison }: ComparisonPanelProps) {
  const [viewMode, setViewMode] = useState<"cards" | "radar" | "bar">("cards");

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>Comparison Analysis</h2>
          <p>Compare multiple task runs by scorecard and metric spread.</p>
        </div>
        {comparison && comparison.items.length > 0 && (
          <div className="charts-tabs">
            <button
              type="button"
              className={`charts-tab ${viewMode === "cards" ? "active" : ""}`}
              onClick={() => setViewMode("cards")}
            >
              Cards
            </button>
            <button
              type="button"
              className={`charts-tab ${viewMode === "radar" ? "active" : ""}`}
              onClick={() => setViewMode("radar")}
            >
              Radar
            </button>
            <button
              type="button"
              className={`charts-tab ${viewMode === "bar" ? "active" : ""}`}
              onClick={() => setViewMode("bar")}
            >
              Bar Chart
            </button>
          </div>
        )}
      </div>

      {!comparison || comparison.items.length === 0 ? (
        <p className="empty-state">Select at least one completed task to populate the comparison panel.</p>
      ) : (
        <>
          {viewMode === "cards" && (
            <div className="comparison-grid">
              {comparison.items.map((item) => (
                <article key={item.task_id} className="comparison-card">
                  <h3>{item.task_name}</h3>
                  <p>{item.agent_version} / {item.dataset}</p>
                  <div className="scorecard-row">
                    {Object.entries(item.scorecard).map(([key, value]) => (
                      <div key={key} className="mini-stat">
                        <span>{key}</span>
                        <strong>{value}</strong>
                      </div>
                    ))}
                  </div>
                  <div className="comparison-metrics">
                    {item.scores.map((metric) => (
                      <div key={metric.key} className="metric-line">
                        <span>{metric.label}</span>
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
              <h4>Dimension Comparison</h4>
              {comparison.items.length >= 1 ? (
                <>
                  <DimensionRadarChart
                    metrics={comparison.items[0].scores}
                    compareTo={comparison.items[1]?.scores}
                    taskName={comparison.items[0].task_name}
                    compareTaskName={comparison.items[1]?.task_name || "Compare"}
                  />
                  {comparison.items.length > 2 && (
                    <p style={{ marginTop: 16, color: "#5d6b82", fontSize: 14 }}>
                      Note: Radar chart shows first two tasks. Select only 2 tasks for best comparison.
                    </p>
                  )}
                </>
              ) : (
                <p className="empty-state">No data available for radar chart.</p>
              )}
            </div>
          )}

          {viewMode === "bar" && (
            <div className="chart-card">
              <h4>Metric Breakdown</h4>
              {comparison.items.length >= 1 ? (
                <>
                  <MetricBarChart
                    metrics={comparison.items[0].scores}
                    compareTo={comparison.items[1]?.scores}
                    taskName={comparison.items[0].task_name}
                    compareTaskName={comparison.items[1]?.task_name || "Compare"}
                    maxHeight={500}
                  />
                  {comparison.items.length > 2 && (
                    <p style={{ marginTop: 16, color: "#5d6b82", fontSize: 14 }}>
                      Note: Bar chart shows first two tasks. Select only 2 tasks for best comparison.
                    </p>
                  )}
                </>
              ) : (
                <p className="empty-state">No data available for bar chart.</p>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
