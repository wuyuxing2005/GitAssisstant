import type {
  BadCaseCreate,
  BadCaseListResponse,
  BadCaseRecord,
  BadCaseRerunRequest,
  BadCaseUpdate,
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
  GitHubIssueLabelsRequest,
  GitHubIssueLabelsResponse,
  GitHubIssueStateRequest,
  GitHubIssueStateResponse,
  GitPullRequestRequest,
  GitPullRequestResponse,
  GitPushRequest,
  GitPushResponse,
  ModelListResponse,
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

export async function updateTaskIssueLabels(
  taskId: string,
  payload: GitHubIssueLabelsRequest
): Promise<GitHubIssueLabelsResponse> {
  return request<GitHubIssueLabelsResponse>(`/tasks/${taskId}/issue/labels`, {
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

export function analyticsReportUrl(format: "md" | "csv", taskIds: string[], badCaseIds: string[]): string {
  const query = new URLSearchParams();
  taskIds.forEach((taskId) => query.append("task_ids", taskId));
  badCaseIds.forEach((caseId) => query.append("bad_case_ids", caseId));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return `${API_ROOT}/analytics/report.${format}${suffix}`;
}

export async function fetchBadCases(): Promise<BadCaseListResponse> {
  return request<BadCaseListResponse>("/bad-cases/");
}

export async function createBadCase(payload: BadCaseCreate): Promise<BadCaseRecord> {
  return request<BadCaseRecord>("/bad-cases/", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateBadCase(caseId: string, payload: BadCaseUpdate): Promise<BadCaseRecord> {
  return request<BadCaseRecord>(`/bad-cases/${caseId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export async function deleteBadCase(caseId: string): Promise<void> {
  await request(`/bad-cases/${caseId}`, { method: "DELETE" });
}

export async function rerunBadCase(
  caseId: string,
  payload: BadCaseRerunRequest
): Promise<EvaluationTask> {
  return request<EvaluationTask>(`/bad-cases/${caseId}/rerun`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchSkills(): Promise<SkillListResponse> {
  return request<SkillListResponse>("/skills/");
}

export async function updateSkillEnabled(name: string, enabled: boolean): Promise<SkillRecord> {
  return request<SkillRecord>(`/skills/${encodeURIComponent(name)}/enabled`, {
    method: "PUT",
    body: JSON.stringify({ enabled })
  });
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
