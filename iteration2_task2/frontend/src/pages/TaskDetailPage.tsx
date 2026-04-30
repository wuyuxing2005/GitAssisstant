import type { EvaluationResult, EvaluationTask } from "../types/task";
import { TraceViewer } from "../components/TraceViewer";

interface TaskDetailPageProps {
  task?: EvaluationTask;
  result?: EvaluationResult;
}

export function TaskDetailPage({ task, result }: TaskDetailPageProps) {
  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>Single Task Analysis</h2>
          <p>{task ? task.name : "Select a task from the table"}</p>
        </div>
      </div>
      {!task ? (
        <p className="empty-state">No task selected.</p>
      ) : (
        <>
          <div className="score-grid">
            {Object.entries(result?.scorecard ?? {}).map(([key, value]) => (
              <article key={key} className="score-card">
                <span>{key}</span>
                <strong>{value}</strong>
                <small>dimension score</small>
              </article>
            ))}
          </div>
          <div className="detail-grid">
            <article className="detail-card">
              <h3>Task Config</h3>
              <ul>
                <li>Agent version: {task.config.agent_version}</li>
                <li>Dataset: {task.config.dataset}</li>
                <li>Modes: {task.config.evaluation_modes.join(" / ")}</li>
                <li>Methods: {task.config.evaluation_methods.join(" / ")}</li>
                <li>Dimensions: {task.config.dimensions.join(" / ")}</li>
                <li>Built-in metrics: {task.config.builtin_metrics.join(", ")}</li>
                <li>Custom metrics: {task.config.custom_metrics.map((item) => item.label).join(", ") || "None"}</li>
                <li>Strategy: {task.config.strategy.label}</li>
              </ul>
            </article>
            <article className="detail-card">
              <h3>Run Summary</h3>
              <p>{result?.summary ?? "Run this task to generate evaluation results."}</p>
              <div className="timeline-list">
                {result?.timeline.map((event) => (
                  <div key={event.stage} className="timeline-item">
                    <span>{event.stage}</span>
                    <strong>{event.status}</strong>
                    <small>{event.message}</small>
                  </div>
                ))}
              </div>
            </article>
          </div>
          <div className="detail-grid">
            <article className="detail-card">
              <h3>Metric Results</h3>
              <div className="comparison-metrics">
                {result?.metrics.map((metric) => (
                  <div key={metric.key} className="metric-line">
                    <span>{metric.label}</span>
                    <strong>
                      {metric.value} {metric.unit !== "score" ? metric.unit : ""}
                    </strong>
                  </div>
                )) ?? <p className="empty-state">No metrics yet.</p>}
              </div>
            </article>
            <article className="detail-card">
              <h3>Execution Logs</h3>
              <div className="log-list">
                {result?.logs_preview.map((line) => (
                  <code key={line}>{line}</code>
                )) ?? <p className="empty-state">No logs yet.</p>}
              </div>
            </article>
          </div>
          {task && (
            <div className="detail-grid">
              <article className="detail-card" style={{ gridColumn: "1 / -1" }}>
                <h3>Execution Traces</h3>
                <TraceViewer taskId={task.id} />
              </article>
            </div>
          )}
        </>
      )}
    </section>
  );
}
