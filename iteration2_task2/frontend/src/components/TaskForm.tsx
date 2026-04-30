import { useEffect, useState, type FormEvent } from "react";

import type {
  EvaluationMetadata,
  EvaluationTaskCreatePayload,
  EvaluationTask,
  MetricDefinition,
  TaskStatus
} from "../types/task";
import { PromptEditor } from "./PromptEditor";

interface TaskFormProps {
  metadata: EvaluationMetadata;
  tasks: EvaluationTask[];
  onSubmit: (payload: EvaluationTaskCreatePayload) => Promise<void>;
  datasetRefreshKey?: number;
}

function buildCustomMetric(): MetricDefinition {
  return {
    key: "",
    label: "",
    description: "",
    dimension: "quality",
    method: "judge",
    enabled: true
  };
}

export function TaskForm({ metadata, tasks, onSubmit, datasetRefreshKey }: TaskFormProps) {
  const defaultStrategy = metadata.strategy_templates[0];
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<TaskStatus>("draft");
  const [agentVersion, setAgentVersion] = useState(metadata.agent_versions[0] ?? "");
  const [dataset, setDataset] = useState(metadata.datasets[0] ?? "");
  const [modes, setModes] = useState<string[]>(["result"]);
  const [methods, setMethods] = useState<string[]>(["explicit"]);
  const [dimensions, setDimensions] = useState<string[]>(["quality"]);
  const [builtinMetrics, setBuiltinMetrics] = useState<string[]>(defaultStrategy?.metric_keys ?? []);
  const [strategyKey, setStrategyKey] = useState(defaultStrategy?.key ?? "");
  const [customMetrics, setCustomMetrics] = useState<MetricDefinition[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (defaultStrategy && !strategyKey) {
      setStrategyKey(defaultStrategy.key);
      setBuiltinMetrics(defaultStrategy.metric_keys);
    }
  }, [defaultStrategy, strategyKey]);

  useEffect(() => {
    setDataset(metadata.datasets[0] ?? "");
  }, [datasetRefreshKey, metadata.datasets]);

  const selectedStrategy =
    metadata.strategy_templates.find((item) => item.key === strategyKey) ?? defaultStrategy;

  function toggleValue(values: string[], key: string) {
    return values.includes(key) ? values.filter((item) => item !== key) : [...values, key];
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedStrategy) {
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit({
        name,
        description,
        status,
        config: {
          agent_version: agentVersion,
          dataset,
          evaluation_modes: modes as EvaluationTaskCreatePayload["config"]["evaluation_modes"],
          evaluation_methods: methods as EvaluationTaskCreatePayload["config"]["evaluation_methods"],
          dimensions: dimensions as EvaluationTaskCreatePayload["config"]["dimensions"],
          builtin_metrics: builtinMetrics,
          custom_metrics: customMetrics.filter((metric) => metric.key && metric.label),
          strategy: selectedStrategy
        }
      });

      setName(`Task ${tasks.length + 1}`);
      setDescription("");
      setStatus("draft");
      setCustomMetrics([]);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>Create Task</h2>
          <p>Configure evaluation mode, methods, built-in metrics, and custom metric extensions.</p>
        </div>
      </div>
      <form className="task-form" onSubmit={handleSubmit}>
        <label>
          Task Name
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          Description
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
        </label>
        <div className="form-row">
          <label>
            Agent Version
            <select value={agentVersion} onChange={(event) => setAgentVersion(event.target.value)}>
              {metadata.agent_versions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            Dataset
            <select value={dataset} onChange={(event) => setDataset(event.target.value)}>
              {metadata.datasets.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            Initial Status
            <select value={status} onChange={(event) => setStatus(event.target.value as TaskStatus)}>
              {["draft", "scheduled", "running", "completed", "failed"].map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="chip-panel">
          <div>
            <h3>Modes</h3>
            <div className="chip-list">
              {metadata.modes.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`chip ${modes.includes(item.key) ? "active" : ""}`}
                  onClick={() => setModes(toggleValue(modes, item.key))}
                  title={item.label}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <h3>Methods</h3>
            <div className="chip-list">
              {metadata.methods.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`chip ${methods.includes(item.key) ? "active" : ""}`}
                  onClick={() => setMethods(toggleValue(methods, item.key))}
                  title={item.label}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <h3>Dimensions</h3>
            <div className="chip-list">
              {metadata.dimensions.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`chip ${dimensions.includes(item.key) ? "active" : ""}`}
                  onClick={() => setDimensions(toggleValue(dimensions, item.key))}
                  title={item.label}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <label>
          Strategy Template
          <select
            value={strategyKey}
            onChange={(event) => {
              const nextKey = event.target.value;
              const nextStrategy = metadata.strategy_templates.find((item) => item.key === nextKey);
              setStrategyKey(nextKey);
              if (nextStrategy) {
                setBuiltinMetrics(nextStrategy.metric_keys);
              }
            }}
          >
            {metadata.strategy_templates.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <div className="metric-picker">
          <h3>Built-in Metrics</h3>
          <div className="metric-list">
            {metadata.builtin_metrics.map((metric) => {
              const isSelected = builtinMetrics.includes(metric.key);
              return (
                <button
                  key={metric.key}
                  type="button"
                  className={`metric-card-btn ${isSelected ? "selected" : ""}`}
                  onClick={() => setBuiltinMetrics(toggleValue(builtinMetrics, metric.key))}
                >
                  <span className="metric-card-label">{metric.label}</span>
                  <small className="metric-card-meta">{metric.dimension} / {metric.method}</small>
                </button>
              );
            })}
          </div>
        </div>

        <div className="metric-picker">
          <div className="section-header compact">
            <div>
              <h3>Custom Metrics</h3>
              <p>Support extension metrics and composite strategies.</p>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setCustomMetrics([...customMetrics, buildCustomMetric()])}
            >
              Add Metric
            </button>
          </div>
          <div className="custom-metric-list">
            {customMetrics.map((metric, index) => (
              <div key={`${metric.key}-${index}`} className="custom-metric-card">
                <button
                  type="button"
                  className="remove-metric-btn"
                  onClick={() => {
                    const next = customMetrics.filter((_, i) => i !== index);
                    setCustomMetrics(next);
                  }}
                  title="Remove this metric"
                >
                  ×
                </button>
                <div className="custom-metric-fields">
                  <input
                    placeholder="metric_key"
                    value={metric.key}
                    onChange={(event) => {
                      const next = [...customMetrics];
                      next[index] = { ...metric, key: event.target.value };
                      setCustomMetrics(next);
                    }}
                  />
                  <input
                    placeholder="Metric label"
                    value={metric.label}
                    onChange={(event) => {
                      const next = [...customMetrics];
                      next[index] = { ...metric, label: event.target.value };
                      setCustomMetrics(next);
                    }}
                  />
                  <select
                    value={metric.dimension}
                    onChange={(event) => {
                      const next = [...customMetrics];
                      next[index] = { ...metric, dimension: event.target.value as MetricDefinition["dimension"] };
                      setCustomMetrics(next);
                    }}
                  >
                    {metadata.dimensions.map((item) => (
                      <option key={item.key} value={item.key}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                  <select
                    value={metric.method}
                    onChange={(event) => {
                      const next = [...customMetrics];
                      next[index] = { ...metric, method: event.target.value as MetricDefinition["method"] };
                      setCustomMetrics(next);
                    }}
                  >
                    {metadata.methods.map((item) => (
                      <option key={item.key} value={item.key}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                  <textarea
                    placeholder="Description"
                    value={metric.description}
                    onChange={(event) => {
                      const next = [...customMetrics];
                      next[index] = { ...metric, description: event.target.value };
                      setCustomMetrics(next);
                    }}
                    rows={2}
                  />
                </div>
                {metric.method === "judge" && (
                  <div className="prompt-editor-wrapper">
                    <PromptEditor
                      metric={metric}
                      onChange={(updatedMetric) => {
                        const next = [...customMetrics];
                        next[index] = updatedMetric;
                        setCustomMetrics(next);
                      }}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? "Saving..." : "Create Evaluation Task"}
        </button>
      </form>
    </section>
  );
}
