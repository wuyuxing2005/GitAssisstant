import { useEffect, useState, type FormEvent } from "react";

import type {
  EvaluationMetadata,
  EvaluationTaskCreatePayload,
  EvaluationTask,
  MetricDefinition,
  TaskStatus
} from "../types/task";
import { PromptEditor } from "./PromptEditor";
import { labelDimension, labelMethod, labelStatus } from "../utils/labels";

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
  const metricDimensionByKey = Object.fromEntries(
    metadata.builtin_metrics.map((metric) => [metric.key, metric.dimension])
  );
  const dimensionsForMetrics = (metricKeys: string[]) =>
    Array.from(
      new Set(
        metricKeys
          .map((key) => metricDimensionByKey[key])
          .filter(Boolean)
      )
    ) as EvaluationTaskCreatePayload["config"]["dimensions"];

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<TaskStatus>("draft");
  const [dataset, setDataset] = useState(metadata.datasets[0] ?? "");
  const [modes, setModes] = useState<string[]>(["result"]);
  const [methods, setMethods] = useState<string[]>(["explicit"]);
  const [dimensions, setDimensions] = useState<string[]>(
    dimensionsForMetrics(defaultStrategy?.metric_keys ?? []) ?? ["quality"]
  );
  const [builtinMetrics, setBuiltinMetrics] = useState<string[]>(defaultStrategy?.metric_keys ?? []);
  const [strategyKey, setStrategyKey] = useState(defaultStrategy?.key ?? "");
  const [customMetrics, setCustomMetrics] = useState<MetricDefinition[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (defaultStrategy && !strategyKey) {
      setStrategyKey(defaultStrategy.key);
      setBuiltinMetrics(defaultStrategy.metric_keys);
      setDimensions(dimensionsForMetrics(defaultStrategy.metric_keys));
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

  function toggleMetric(metric: MetricDefinition) {
    setBuiltinMetrics((current) => {
      const next = current.includes(metric.key)
        ? current.filter((key) => key !== metric.key)
        : [...current, metric.key];
      setDimensions(dimensionsForMetrics(next));
      return next;
    });
  }

  function toggleDimension(dimensionKey: string) {
    const dimensionMetrics = metadata.builtin_metrics
      .filter((metric) => metric.dimension === dimensionKey)
      .map((metric) => metric.key);

    setDimensions((current) => {
      const isActive = current.includes(dimensionKey);
      setBuiltinMetrics((selected) =>
        isActive
          ? selected.filter((key) => !dimensionMetrics.includes(key))
          : Array.from(new Set([...selected, ...dimensionMetrics]))
      );
      return isActive ? current.filter((key) => key !== dimensionKey) : [...current, dimensionKey];
    });
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
          dataset,
          evaluation_modes: modes as EvaluationTaskCreatePayload["config"]["evaluation_modes"],
          evaluation_methods: methods as EvaluationTaskCreatePayload["config"]["evaluation_methods"],
          dimensions: dimensions as EvaluationTaskCreatePayload["config"]["dimensions"],
          builtin_metrics: builtinMetrics,
          custom_metrics: customMetrics.filter((metric) => metric.key && metric.label),
          strategy: selectedStrategy
        }
      });

      setName(`评测任务 ${tasks.length + 1}`);
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
          <h2>创建评测任务</h2>
          <p>配置评测模式、评测方法、内置指标和自定义指标扩展。</p>
        </div>
      </div>
      <form className="task-form" onSubmit={handleSubmit}>
        <label>
          任务名称
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          任务说明
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
        </label>
        <div className="form-row">
          <label>
            数据集
            <select value={dataset} onChange={(event) => setDataset(event.target.value)}>
              {metadata.datasets.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            初始状态
            <select value={status} onChange={(event) => setStatus(event.target.value as TaskStatus)}>
              {["draft", "scheduled", "running", "completed", "failed"].map((item) => (
                <option key={item} value={item}>
                  {labelStatus(item)}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="chip-panel">
          <div>
            <h3>评测模式</h3>
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
            <h3>评测方法</h3>
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
        </div>

        <label>
          组合评估策略
          <select
            value={strategyKey}
            onChange={(event) => {
              const nextKey = event.target.value;
              const nextStrategy = metadata.strategy_templates.find((item) => item.key === nextKey);
              setStrategyKey(nextKey);
              if (nextStrategy) {
                setBuiltinMetrics(nextStrategy.metric_keys);
                setDimensions(dimensionsForMetrics(nextStrategy.metric_keys));
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
          <div>
            <h3>内置指标</h3>
            <p>先选择评测维度，再勾选该维度下的具体指标。</p>
          </div>
          <div className="dimension-metric-grid">
            {metadata.dimensions.map((dimension) => {
              const dimensionMetrics = metadata.builtin_metrics.filter(
                (metric) => metric.dimension === dimension.key
              );
              const isDimensionSelected = dimensions.includes(dimension.key);

              return (
                <section
                  key={dimension.key}
                  className={`dimension-metric-group ${isDimensionSelected ? "selected" : ""}`}
                >
                  <button
                    type="button"
                    className={`dimension-toggle ${isDimensionSelected ? "active" : ""}`}
                    onClick={() => toggleDimension(dimension.key)}
                  >
                    <span>{labelDimension(dimension.key)}</span>
                    <small>{dimensionMetrics.length} 个指标</small>
                  </button>

                  <div className="metric-list grouped">
                    {dimensionMetrics.map((metric) => {
                      const isSelected = builtinMetrics.includes(metric.key);
                      return (
                        <button
                          key={metric.key}
                          type="button"
                          className={`metric-card-btn ${isSelected ? "selected" : ""}`}
                          onClick={() => toggleMetric(metric)}
                        >
                          <span className="metric-card-label">{metric.label}</span>
                          <small className="metric-card-meta">{labelMethod(metric.method)}</small>
                          <small className="metric-card-description">{metric.description}</small>
                        </button>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>
        </div>

        <div className="metric-picker">
          <div className="section-header compact">
            <div>
              <h3>自定义指标</h3>
              <p>支持按业务需求扩展指标，并纳入组合策略。</p>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setCustomMetrics([...customMetrics, buildCustomMetric()])}
            >
              添加指标
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
                  title="移除该指标"
                >
                  ×
                </button>
                <div className="custom-metric-fields">
                  <input
                    placeholder="指标 key，例如 policy_compliance"
                    value={metric.key}
                    onChange={(event) => {
                      const next = [...customMetrics];
                      next[index] = { ...metric, key: event.target.value };
                      setCustomMetrics(next);
                    }}
                  />
                  <input
                    placeholder="指标名称"
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
                    placeholder="指标说明"
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
          {submitting ? "保存中..." : "创建评测任务"}
        </button>
      </form>
    </section>
  );
}
