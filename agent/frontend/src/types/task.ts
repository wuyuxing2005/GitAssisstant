export type TaskStatus = "draft" | "scheduled" | "running" | "interrupted" | "completed" | "failed";
export type RunMode = "auto";
export type ExecutionOutcome = "not_started" | "running" | "interrupted" | "completed" | "failed";

export interface EvaluationConfig {
  repo_source: string;
  issue_input: string;
  target_dir?: string | null;
  model_name?: string | null;
  run_mode: RunMode;
  enabled_skills?: string[] | null;
}

export interface ToolCallRecord {
  name: string;
  args: Record<string, unknown>;
}

export interface SandboxEventStepRecord {
  phase: string;
  status: string;
  title: string;
  command: string;
  started_at?: string | null;
  finished_at?: string | null;
  elapsed_ms?: number | null;
  output_tail: string[];
  error_message: string;
}

export interface SandboxEventRecord {
  phase: string;
  status: string;
  title: string;
  command: string;
  started_at?: string | null;
  finished_at?: string | null;
  elapsed_ms?: number | null;
  output_tail: string[];
  error_message: string;
  steps: SandboxEventStepRecord[];
}

export interface ToolCallInfo {
  name: string;
  arguments: Record<string, unknown>;
  result_preview: string;
  error_message: string;
  exit_code?: number | null;
  latency_ms: number;
  risk_level: string;
  sandbox_id: string;
  affected_files: string[];
}

export interface TraceEvent {
  event_id: string;
  seq: number;
  parent_event_id?: string | null;
  timestamp: string;
  event_type: string;
  phase: string;
  actor: "user" | "agent" | "tool" | "system" | string;
  status: string;
  title: string;
  content: string;
  duration_ms?: number | null;
  tool_call?: ToolCallInfo | null;
  metadata: Record<string, unknown>;
}

export interface AgentTraceRepoInfo {
  repo_url: string;
  branch: string;
  commit: string;
  sandbox_id: string;
}

export interface AgentTrace {
  schema_version: string;
  trace_id: string;
  task_id: string;
  conversation_id: string;
  issue_id: string;
  agent_version: string;
  repo: AgentTraceRepoInfo;
  user_input: string;
  final_response: string;
  status: string;
  started_at?: string | null;
  ended_at?: string | null;
  total_latency_ms?: number | null;
  token_usage: Record<string, number>;
  events: TraceEvent[];
  failure_type?: string | null;
  failure_reason?: string | null;
  related_event_ids: string[];
  suggested_fix?: string | null;
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

export type TaskMessageRole = "user" | "assistant" | "system";
export type TaskMessageKind = "text" | "tool_call" | "sandbox_event";

export interface TaskMessage {
  id: string;
  role: TaskMessageRole;
  content: string;
  created_at: string;
  replan: boolean;
  kind?: TaskMessageKind;
  tool_calls?: ToolCallRecord[];
  sandbox_event?: SandboxEventRecord | null;
}

export interface TaskMessageCreate {
  content: string;
  replan: boolean;
}

export interface TaskMessageList {
  task_id: string;
  messages: TaskMessage[];
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
  sandbox_id: string;
  issue_description?: string | null;
  status: string;
  iteration_count: number;
  plan: string[];
  reflexion_notes: string;
  last_message: string;
  selected_skill: string;
}

export interface EvaluationResult {
  task_id: string;
  summary: string;
  outcome: ExecutionOutcome;
  metrics: MetricScore[];
  logs_preview: string[];
  tool_usage: ToolUsageItem[];
  timeline: TimelineEntry[];
  agent_trace?: AgentTrace | null;
  messages: TaskMessage[];
  current_state?: RuntimeSnapshot | null;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
  fix_report?: FixReport | null;
  last_commit_hash?: string | null;
  pull_request_url?: string | null;
}

export interface FixReport {
  file_name: string;
  markdown: string;
  suggested_pr_title: string;
  suggested_pr_description: string;
  created_at: string;
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
  has_unpublished_changes?: boolean;
}

export interface GitDiffResponse {
  task_id: string;
  repo_path: string;
  branch: string;
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

export interface GitPullRequestRequest {
  commit_message?: string | null;
  title?: string | null;
  body?: string | null;
  remote?: string;
  branch?: string | null;
  base_branch?: string | null;
}

export interface GitPullRequestResponse {
  task_id: string;
  repo_path: string;
  branch: string;
  base_branch: string;
  commit_hash?: string | null;
  pr_url?: string | null;
  output: string;
}

export interface GitHubIssueComment {
  id: number;
  user: string;
  body: string;
  html_url: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface GitHubIssueInfo {
  task_id: string;
  owner: string;
  repo: string;
  number: number;
  title: string;
  body: string;
  state: "open" | "closed" | string;
  state_reason?: string | null;
  labels: string[];
  html_url: string;
  comments_count: number;
  comments: GitHubIssueComment[];
  default_comment: string;
}

export interface GitHubIssueCommentRequest {
  body: string;
}

export interface GitHubIssueSummary {
  number: number;
  title: string;
  body: string;
  state: string;
  labels: string[];
  html_url: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface GitHubIssueCommentResponse {
  id: number;
  html_url: string;
  body: string;
}

export interface GitHubIssueStateRequest {
  state: "closed";
  state_reason?: "completed" | "not_planned" | null;
}

export interface GitHubIssueStateResponse {
  state: string;
  state_reason?: string | null;
  html_url: string;
}

export interface ComparisonItem {
  task_id: string;
  task_name: string;
  status: TaskStatus;
  summary: string;
  scores: MetricScore[];
}

export interface ComparisonAggregate {
  success_rate: number;
  failed_count: number;
  average_duration_seconds: number;
  average_tool_call_count: number;
  average_test_run_count: number;
}

export interface ComparisonResponse {
  compared_metrics: string[];
  items: ComparisonItem[];
  aggregate: ComparisonAggregate;
}

export interface SkillRecord {
  name: string;
  description: string;
  allowed_tools: string[];
  priority_tools: string[];
  body: string;
  enabled: boolean;
  builtin: boolean;
}

export interface SkillListResponse {
  items: SkillRecord[];
}

export interface SkillCreateRequest {
  name: string;
  description: string;
  allowed_tools: string[];
  priority_tools: string[];
  body: string;
  enabled: boolean;
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
  auto_start?: boolean;
  config: EvaluationConfig;
}

export interface TaskRunRequest {
  mode?: RunMode;
  reset: boolean;
  allow_local_fallback?: boolean;
}

export interface AppSettings {
  openai_api_key_set: boolean;
  github_token_set: boolean;
  openai_api_key: string;
  github_token: string;
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

export interface LongTermMemoryRecord {
  id: string;
  task_id: string;
  task_name: string;
  repo_source: string;
  issue_input: string;
  outcome: string;
  content: string;
  tags: string[];
  source: "llm" | "rule" | string;
  created_at: string;
  updated_at: string;
}

export interface LongTermMemoryListResponse {
  items: LongTermMemoryRecord[];
}

export interface LongTermMemoryRebuildResponse {
  count: number;
  skipped_count: number;
  items: LongTermMemoryRecord[];
}
