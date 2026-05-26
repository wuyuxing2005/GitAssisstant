import type {
  ComparisonResponse,
  AppSettings,
  AppSettingsUpdate,
  CreateTaskPayload,
  EvaluationMetadataResponse,
  EvaluationTask,
  GitDiffResponse,
  GitPushRequest,
  GitPushResponse,
  ModelListResponse,
  TaskRunRequest
} from "../types/task";

const API_ROOT = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";
const HEALTH_ROOT = API_ROOT.replace(/\/api\/?$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      detail = response.statusText;
    }
    throw new Error(detail || "请求失败");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function fetchHealth(): Promise<{ status: string }> {
  const response = await fetch(`${HEALTH_ROOT}/health`);
  if (!response.ok) {
    throw new Error("后端不可用");
  }
  return (await response.json()) as { status: string };
}

export async function fetchTasks(): Promise<EvaluationTask[]> {
  return request<EvaluationTask[]>("/tasks/");
}

export async function createTask(payload: CreateTaskPayload): Promise<EvaluationTask> {
  return request<EvaluationTask>("/tasks/", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function runTask(taskId: string, payload: TaskRunRequest): Promise<EvaluationTask> {
  return request<EvaluationTask>(`/tasks/${taskId}/run`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function deleteTask(taskId: string): Promise<void> {
  await request(`/tasks/${taskId}`, { method: "DELETE" });
}

export async function fetchTaskDiff(taskId: string): Promise<GitDiffResponse> {
  return request<GitDiffResponse>(`/tasks/${taskId}/diff`);
}

export async function pushTaskChanges(
  taskId: string,
  payload: GitPushRequest
): Promise<GitPushResponse> {
  return request<GitPushResponse>(`/tasks/${taskId}/push`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchMetadata(): Promise<EvaluationMetadataResponse> {
  return request<EvaluationMetadataResponse>("/metadata/evaluation-options");
}

export async function compareTasks(taskIds: string[]): Promise<ComparisonResponse> {
  const query = new URLSearchParams();
  taskIds.forEach((taskId) => query.append("task_ids", taskId));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<ComparisonResponse>(`/analytics/compare${suffix}`);
}

export async function fetchSettings(): Promise<AppSettings> {
  return request<AppSettings>("/settings/");
}

export async function updateSettings(payload: AppSettingsUpdate): Promise<AppSettings> {
  return request<AppSettings>("/settings/", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function fetchOpenAIModels(): Promise<ModelListResponse> {
  return request<ModelListResponse>("/settings/models");
}
