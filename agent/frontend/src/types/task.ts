export type TaskStatus = "draft" | "scheduled" | "running" | "completed" | "failed";
export type RunMode = "auto" | "step";
export type ExecutionOutcome = "not_started" | "running" | "completed" | "failed";

export interface EvaluationConfig {
  repo_source: string;
  issue_input: string;
  target_dir?: string | null;
  model_name?: string | null;
  max_iterations: number;
  run_mode: RunMode;
}

export interface ToolCallRecord {
  name: string;
  args: Record<string, unknown>;
}

export interface TimelineEntry {
  id: string;
  node: string;
  event_type: string;
  title: string;
  content: string;
  tool_calls: ToolCallRecord[];
  created_at: string;
}

export interface ToolUsageItem {
  name: string;
  count: number;
}

export interface MetricScore {
  name: string;
  value: number;
  category: string;
  unit?: string | null;
  description?: string | null;
}

export interface RuntimeSnapshot {
  thread_id?: string | null;
  repo_path?: string | null;
  issue_description?: string | null;
  status: string;
  iteration_count: number;
  max_iterations: number;
  plan: string[];
  reflexion_notes: string;
  last_message: string;
}

export interface EvaluationResult {
  task_id: string;
  summary: string;
  outcome: ExecutionOutcome;
  metrics: MetricScore[];
  logs_preview: string[];
  tool_usage: ToolUsageItem[];
  timeline: TimelineEntry[];
  current_state?: RuntimeSnapshot | null;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
}

export interface EvaluationTask {
  id: string;
  name: string;
  description: string;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  config: EvaluationConfig;
  result?: EvaluationResult | null;
}

export interface GitDiffResponse {
  task_id: string;
  repo_path: string;
  status: string;
  diff: string;
  has_changes: boolean;
}

export interface GitPushRequest {
  commit_message?: string | null;
  remote?: string;
  branch?: string | null;
}

export interface GitPushResponse {
  task_id: string;
  repo_path: string;
  commit_hash?: string | null;
  pushed: boolean;
  output: string;
}

export interface ComparisonItem {
  task_id: string;
  task_name: string;
  status: TaskStatus;
  summary: string;
  scores: MetricScore[];
}

export interface ComparisonResponse {
  compared_metrics: string[];
  items: ComparisonItem[];
}

export interface ToolDescriptor {
  name: string;
  category: string;
  summary: string;
}

export interface EvaluationMetadataResponse {
  modes: string[];
  methods: string[];
  dimensions: string[];
  builtin_metrics: string[];
  strategy_templates: string[];
  builtin_tools: ToolDescriptor[];
  runtime_requirements: string[];
}

export interface CreateTaskPayload {
  name: string;
  description: string;
  config: EvaluationConfig;
  auto_start: boolean;
}

export interface TaskRunRequest {
  mode?: RunMode;
  reset: boolean;
}

export interface AppSettings {
  openai_api_key_set: boolean;
  github_token_set: boolean;
  openai_base_url: string;
  model_name: string;
  clone_root: string;
  env_path: string;
}

export interface AppSettingsUpdate {
  openai_api_key?: string | null;
  github_token?: string | null;
  openai_base_url?: string | null;
  model_name?: string | null;
  clone_root?: string | null;
}

export interface ModelListResponse {
  models: string[];
}
