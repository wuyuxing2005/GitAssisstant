import type { EvaluationTask, TaskStatus } from "../types/task";

const terminalRuntimeStatuses = new Set(["SUCCESS", "FAILED"]);
const queuedRuntimeStatuses = new Set(["", "INIT", "SANDBOX_UNAVAILABLE"]);

export function getEffectiveTaskStatus(task: EvaluationTask): TaskStatus {
  if (task.status !== "scheduled") {
    return task.status;
  }

  const runtimeStatus = (task.result?.current_state?.status || "").trim().toUpperCase();
  if (!runtimeStatus || queuedRuntimeStatuses.has(runtimeStatus)) {
    return "scheduled";
  }
  if (terminalRuntimeStatuses.has(runtimeStatus)) {
    return runtimeStatus === "SUCCESS" ? "completed" : "failed";
  }
  return "running";
}

export function formatTaskStatus(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    draft: "草稿",
    scheduled: "排队中",
    running: "执行中",
    completed: "已完成",
    failed: "失败"
  };

  return labels[status];
}
