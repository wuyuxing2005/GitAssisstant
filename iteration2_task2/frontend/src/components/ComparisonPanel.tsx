import type { ComparisonResponse } from "../types/task";

interface ComparisonPanelProps {
  comparison?: ComparisonResponse;
}

export function ComparisonPanel({ comparison }: ComparisonPanelProps) {
  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>Comparison Analysis</h2>
          <p>Compare multiple task runs by scorecard and metric spread.</p>
        </div>
      </div>
      {!comparison || comparison.items.length === 0 ? (
        <p className="empty-state">Select at least one completed task to populate the comparison panel.</p>
      ) : (
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
    </section>
  );
}
