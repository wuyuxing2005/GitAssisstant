import type {
  AgentTrace,
  ComparisonResponse,
  AppSettings,
  AppSettingsUpdate,
  CreateTaskPayload,
  EvaluationMetadataResponse,
  EvaluationTask,
  GitDiffResponse,
  GitHubIssueCommentRequest,
  GitHubIssueCommentResponse,
  GitHubIssueInfo,
  GitHubIssueStateRequest,
  GitHubIssueStateResponse,
  GitHubIssueSummary,
  GitPullRequestRequest,
  GitPullRequestResponse,
  GitPushRequest,
  GitPushResponse,
  ModelListResponse,
  LongTermMemoryListResponse,
  LongTermMemoryRebuildResponse,
  SkillCreateRequest,
  SkillListResponse,
  SkillRecord,
  TaskMessageCreate,
  TaskMessageList,
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

export async function terminateSandboxTask(taskId: string): Promise<EvaluationTask> {
  return request<EvaluationTask>(`/tasks/${taskId}/sandbox/terminate`, {
    method: "POST"
  });
}

export async function interruptTask(taskId: string): Promise<EvaluationTask> {
  return request<EvaluationTask>(`/tasks/${taskId}/interrupt`, {
    method: "POST"
  });
}

export async function deleteTask(taskId: string): Promise<void> {
  await request(`/tasks/${taskId}`, { method: "DELETE" });
}

export async function fetchTaskMessages(taskId: string): Promise<TaskMessageList> {
  return request<TaskMessageList>(`/tasks/${taskId}/messages`);
}

export async function submitTaskMessage(
  taskId: string,
  payload: TaskMessageCreate
): Promise<TaskMessageList> {
  return request<TaskMessageList>(`/tasks/${taskId}/messages`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchTaskDiff(taskId: string): Promise<GitDiffResponse> {
  return request<GitDiffResponse>(`/tasks/${taskId}/diff`);
}

export async function fetchTaskTrace(taskId: string): Promise<AgentTrace> {
  return request<AgentTrace>(`/tasks/${taskId}/trace`);
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

export async function createTaskPullRequest(
  taskId: string,
  payload: GitPullRequestRequest
): Promise<GitPullRequestResponse> {
  return request<GitPullRequestResponse>(`/tasks/${taskId}/pull-request`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchTaskIssue(taskId: string): Promise<GitHubIssueInfo> {
  return request<GitHubIssueInfo>(`/tasks/${taskId}/issue`);
}

export async function commentTaskIssue(
  taskId: string,
  payload: GitHubIssueCommentRequest
): Promise<GitHubIssueCommentResponse> {
  return request<GitHubIssueCommentResponse>(`/tasks/${taskId}/issue/comment`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateTaskIssueState(
  taskId: string,
  payload: GitHubIssueStateRequest
): Promise<GitHubIssueStateResponse> {
  return request<GitHubIssueStateResponse>(`/tasks/${taskId}/issue/state`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function taskReportDownloadUrl(taskId: string): string {
  return `${API_ROOT}/tasks/${taskId}/report`;
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

export function analyticsReportUrl(format: "md" | "csv", taskIds: string[]): string {
  const query = new URLSearchParams();
  taskIds.forEach((taskId) => query.append("task_ids", taskId));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return `${API_ROOT}/analytics/report.${format}${suffix}`;
}

export async function fetchSkills(): Promise<SkillListResponse> {
  return request<SkillListResponse>("/skills/");
}

export async function createSkill(payload: SkillCreateRequest): Promise<SkillRecord> {
  return request<SkillRecord>("/skills/", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateSkillEnabled(name: string, enabled: boolean): Promise<SkillRecord> {
  return request<SkillRecord>(`/skills/${encodeURIComponent(name)}/enabled`, {
    method: "PUT",
    body: JSON.stringify({ enabled })
  });
}

export async function deleteSkill(name: string): Promise<void> {
  await request(`/skills/${encodeURIComponent(name)}`, { method: "DELETE" });
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

export async function fetchMemories(limit: number = 50): Promise<LongTermMemoryListResponse> {
  return request<LongTermMemoryListResponse>(`/memories/?limit=${limit}`);
}

export async function rebuildMemories(limit: number = 20): Promise<LongTermMemoryRebuildResponse> {
  return request<LongTermMemoryRebuildResponse>("/memories/rebuild", {
    method: "POST",
    body: JSON.stringify({ limit })
  });
}

export async function deleteMemory(memoryId: string): Promise<void> {
  await request(`/memories/${encodeURIComponent(memoryId)}`, { method: "DELETE" });
}

export async function clearMemories(): Promise<{ count: number }> {
  return request<{ count: number }>("/memories/", { method: "DELETE" });
}

export async function fetchRepoIssues(
  url: string,
  state: string = "open",
  perPage: number = 30
): Promise<GitHubIssueSummary[]> {
  const query = new URLSearchParams({ url, state, per_page: String(perPage) });
  return request<GitHubIssueSummary[]>(`/repos/issues?${query.toString()}`);
}
