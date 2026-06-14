import type { EvaluationTask, TaskStatus } from "../types/task";

const terminalRuntimeStatuses = new Set(["SUCCESS", "FAILED"]);
const interruptedRuntimeStatuses = new Set(["INTERRUPTED"]);
const queuedRuntimeStatuses = new Set(["", "INIT", "SANDBOX_UNAVAILABLE"]);

export function getEffectiveTaskStatus(task: EvaluationTask): TaskStatus {
  if (task.status === "scheduled") {
    const runtimeStatus = (task.result?.current_state?.status || "").trim().toUpperCase();
    if (runtimeStatus === "INTERRUPTED") {
      return "scheduled";
    }
  }

  if (task.status !== "scheduled") {
    return task.status;
  }

  const runtimeStatus = (task.result?.current_state?.status || "").trim().toUpperCase();
  if (runtimeStatus !== "SANDBOX_UNAVAILABLE" && (task.result?.outcome === "running" || task.result?.started_at)) {
    return "running";
  }
  if (!runtimeStatus || queuedRuntimeStatuses.has(runtimeStatus)) {
    return "scheduled";
  }
  if (terminalRuntimeStatuses.has(runtimeStatus)) {
    return runtimeStatus === "SUCCESS" ? "completed" : "failed";
  }
  if (interruptedRuntimeStatuses.has(runtimeStatus)) {
    return "interrupted";
  }
  return "running";
}

export function formatTaskStatus(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    draft: "草稿",
    scheduled: "排队中",
    running: "执行中",
    interrupted: "已中断",
    completed: "已完成",
    failed: "失败"
  };

  return labels[status];
}

export function getTaskDisplayStatus(task: EvaluationTask, hasUnpublishedChanges = !!task.has_unpublished_changes): string {
  const effectiveStatus = getEffectiveTaskStatus(task);
  if (effectiveStatus === "completed" && hasUnpublishedChanges) {
    return "等待发布";
  }
  return formatTaskStatus(effectiveStatus);
}
