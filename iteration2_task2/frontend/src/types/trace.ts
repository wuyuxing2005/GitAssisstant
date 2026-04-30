export interface ToolCallInfo {
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  status: "success" | "error";
  latency_ms: number;
}

export type TraceEventType =
  | "tool_call"
  | "tool_result"
  | "llm_generation"
  | "user_input"
  | "system_message"
  | "error";

export interface TraceEvent {
  id: string;
  timestamp: string;
  event_type: TraceEventType;
  message?: string;
  tool_call?: ToolCallInfo;
  metadata?: Record<string, unknown>;
}

export interface AgentTrace {
  trace_id: string;
  task_id: string;
  sample_id: string;
  user_input: string;
  final_response: string;
  events: TraceEvent[];
  total_latency_ms: number;
  token_usage: {
    prompt: number;
    completion: number;
    total: number;
  };
}

export interface TraceAnalysisResult {
  sample_id: string;
  tool_accuracy: number;
  reasoning_quality: number;
  process_completeness: number;
  issues: string[];
}
