import type {
  ComparisonResponse,
  EvaluationMetadata,
  EvaluationResult,
  EvaluationTask,
  EvaluationTaskCreatePayload,
  TaskStatus
} from "../types/task";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
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
