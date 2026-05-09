export type TaskStatus = "draft" | "scheduled" | "running" | "completed" | "failed";
export type EvaluationMode = "result" | "process";
export type EvaluationMethod = "explicit" | "judge";
export type EvaluationDimension = "quality" | "safety" | "performance";

export interface MetadataOption {
  key: string;
  label: string;
}

export interface MetricDefinition {
  key: string;
  label: string;
  description: string;
  dimension: EvaluationDimension;
  method: EvaluationMethod;
  enabled: boolean;
  judge_prompt?: {
    template_key?: string;
    custom_prompt?: string;
    criteria?: Record<string, string>;
  };
}

export interface EvaluationStrategy {
  key: string;
  label: string;
  description: string;
  metric_keys: string[];
  weights: Record<string, number>;
}

export interface EvaluationConfig {
  dataset: string;
  evaluation_modes: EvaluationMode[];
  evaluation_methods: EvaluationMethod[];
  dimensions: EvaluationDimension[];
  builtin_metrics: string[];
  custom_metrics: MetricDefinition[];
  strategy: EvaluationStrategy;
}

export interface EvaluationTask {
  id: string;
  name: string;
  description: string;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  config: EvaluationConfig;
}

export interface MetricScore {
  key: string;
  label: string;
  value: number;
  unit: string;
  category: EvaluationDimension;
  method: EvaluationMethod;
  source: "builtin" | "custom";
  description: string;
}

export interface EvaluationTimelineEvent {
  stage: string;
  status: "pending" | "running" | "completed";
  message: string;
}

export interface EvaluationResult {
  task_id: string;
  task_name: string;
  summary: string;
  status: TaskStatus;
  scorecard: Record<string, number>;
  metrics: MetricScore[];
  timeline: EvaluationTimelineEvent[];
  charts: string[];
  logs_preview: string[];
}

export interface ComparisonItem {
  task_id: string;
  task_name: string;
  dataset: string;
  status: TaskStatus;
  scorecard: Record<string, number>;
  scores: MetricScore[];
}

export interface ComparisonResponse {
  compared_metrics: string[];
  items: ComparisonItem[];
}

export interface EvaluationMetadata {
  modes: MetadataOption[];
  methods: MetadataOption[];
  dimensions: MetadataOption[];
  builtin_metrics: MetricDefinition[];
  strategy_templates: EvaluationStrategy[];
  datasets: string[];
}

export interface EvaluationTaskCreatePayload {
  name: string;
  description: string;
  status: TaskStatus;
  config: EvaluationConfig;
}
