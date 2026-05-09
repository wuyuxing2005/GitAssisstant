import type {
  ComparisonResponse,
  EvaluationMetadata,
  EvaluationResult,
  EvaluationTask,
  EvaluationTaskCreatePayload,
  TaskStatus
} from "../types/task";
import type { AgentTrace } from "../types/trace";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;

  // 对于 FormData，不设置 Content-Type，让浏览器自动设置（包括 boundary）
  const headers: HeadersInit = isFormData ? {} : {
    "Content-Type": "application/json",
    ...(init?.headers ?? {})
  };

  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    ...init
  });

  if (!response.ok) {
    // 尝试解析错误详情
    try {
      const errorData = await response.json();
      const errorMsg = errorData.detail || errorData.message || `接口请求失败：${response.status}`;
      throw new Error(errorMsg);
    } catch {
      throw new Error(`接口请求失败：${response.status}`);
    }
  }

  return response.json() as Promise<T>;
}

export function fetchTasks(): Promise<EvaluationTask[]> {
  return request<EvaluationTask[]>("/tasks/");
}

export function createTask(payload: EvaluationTaskCreatePayload): Promise<EvaluationTask> {
  return request<EvaluationTask>("/tasks/", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateTaskStatus(taskId: string, status: TaskStatus): Promise<EvaluationTask> {
  return request<EvaluationTask>(`/tasks/${taskId}`, {
    method: "PUT",
    body: JSON.stringify({ status })
  });
}

export function deleteTask(taskId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/tasks/${taskId}`, {
    method: "DELETE"
  });
}

export function runTask(taskId: string): Promise<EvaluationResult> {
  return request<EvaluationResult>(`/tasks/${taskId}/run`, {
    method: "POST"
  });
}

export function fetchTaskResult(taskId: string): Promise<EvaluationResult> {
  return request<EvaluationResult>(`/tasks/${taskId}/results`);
}

export function fetchComparison(taskIds: string[]): Promise<ComparisonResponse> {
  const query = new URLSearchParams();
  taskIds.forEach((taskId) => query.append("task_ids", taskId));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<ComparisonResponse>(`/analytics/compare${suffix}`);
}

export function fetchEvaluationMetadata(): Promise<EvaluationMetadata> {
  return request<EvaluationMetadata>("/metadata/evaluation-options");
}

// Trace API
export function fetchTraces(taskId: string): Promise<AgentTrace[]> {
  return request<AgentTrace[]>(`/traces/${taskId}`);
}

export function fetchTrace(taskId: string, sampleId: string): Promise<AgentTrace> {
  return request<AgentTrace>(`/traces/${taskId}/${sampleId}`);
}

export function uploadTrace(traceData: Partial<AgentTrace>): Promise<{ message: string; trace_id: string; task_id: string; sample_id: string }> {
  return request<{ message: string; trace_id: string; task_id: string; sample_id: string }>("/traces/upload", {
    method: "POST",
    body: JSON.stringify(traceData)
  });
}

export function uploadTracesBatch(traces: Partial<AgentTrace>[]): Promise<{ message: string; success_count: number; failed_count: number; errors?: { index: number; error: string }[] }> {
  return request<{ message: string; success_count: number; failed_count: number; errors?: { index: number; error: string }[] }>("/traces/upload/batch", {
    method: "POST",
    body: JSON.stringify(traces)
  });
}

export function deleteTraces(taskId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/traces/${taskId}`, {
    method: "DELETE"
  });
}

// Dataset API
export interface DatasetInfo {
  name: string;
  file_name: string;
  line_count: number;
  size_bytes: number;
  created_at: number;
  modified_at: number;
}

export interface DatasetDetail extends DatasetInfo {
  preview: Record<string, unknown>[];
}

export function fetchDatasets(): Promise<DatasetInfo[]> {
  return request<DatasetInfo[]>("/datasets/");
}

export function fetchDatasetDetail(name: string, limit?: number): Promise<DatasetDetail> {
  const query = limit ? `?limit=${limit}` : "";
  return request<DatasetDetail>(`/datasets/${name}${query}`);
}

export function uploadDataset(file: File): Promise<{ message: string; dataset_name: string; file_path: string; line_count: number }> {
  const formData = new FormData();
  formData.append("file", file);
  return request<{ message: string; dataset_name: string; file_path: string; line_count: number }>("/datasets/upload", {
    method: "POST",
    body: formData
  });
}

export function deleteDataset(name: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/datasets/${name}`, {
    method: "DELETE"
  });
}

// Report API
export function exportReport(taskId: string, format: "json" | "md" = "json"): Promise<Blob> {
  return fetch(`${API_BASE}/reports/${taskId}?format=${format}`, {
    method: "GET"
  }).then(async (response) => {
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || errorData.message || `导出失败：${response.status}`);
    }
    return response.blob();
  });
}

export function downloadReport(taskId: string, format: "json" | "md" = "json"): void {
  exportReport(taskId, format).then((blob) => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${taskId}_report.${format === "md" ? "md" : "json"}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  }).catch(console.error);
}
