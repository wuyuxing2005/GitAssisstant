import type { EvaluationDimension, EvaluationMethod, EvaluationMode, TaskStatus } from "../types/task";

export const statusLabels: Record<TaskStatus, string> = {
  draft: "草稿",
  scheduled: "已排队",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

export const modeLabels: Record<EvaluationMode, string> = {
  result: "面向结果",
  process: "面向过程",
};

export const methodLabels: Record<EvaluationMethod, string> = {
  explicit: "显式指标",
  judge: "LLM 评审",
};

export const dimensionLabels: Record<EvaluationDimension, string> = {
  quality: "效果",
  safety: "安全",
  performance: "性能",
};

export const metricLabels: Record<string, string> = {
  answer_correctness: "答案正确性",
  faithfulness: "忠实性",
  task_success_rate: "任务成功率",
  tool_accuracy: "工具调用准确率",
  reasoning_quality: "推理质量",
  hallucination_risk: "幻觉控制",
  safety: "安全性",
  latency: "延迟得分",
  response_time: "首响应得分",
  token_usage: "Token 效率",
  interaction_experience: "交互体验",
};

export const timelineStageLabels: Record<string, string> = {
  "task-prepare": "任务准备",
  "process-signals": "过程信号",
  "trace-collect": "执行链路采集",
  "ragas-evaluate": "Ragas 评估",
  "metric-evaluate": "指标评估",
  "result-aggregate": "结果聚合",
  "dataset-load": "数据集加载",
  "ragas-run": "Ragas 执行",
};

export const timelineStatusLabels: Record<string, string> = {
  pending: "待执行",
  running: "运行中",
  completed: "已完成",
};

export const traceEventLabels: Record<string, string> = {
  tool_call: "工具调用",
  tool_result: "工具结果",
  llm_generation: "模型生成",
  user_input: "用户输入",
  system_message: "系统消息",
  error: "错误",
};

export function labelStatus(status: string): string {
  return statusLabels[status as TaskStatus] ?? status;
}

export function labelMode(mode: string): string {
  return modeLabels[mode as EvaluationMode] ?? mode;
}

export function labelMethod(method: string): string {
  return methodLabels[method as EvaluationMethod] ?? method;
}

export function labelDimension(dimension: string): string {
  return dimensionLabels[dimension as EvaluationDimension] ?? dimension;
}

export function labelMetric(key: string, fallback: string): string {
  return metricLabels[key] ?? fallback;
}

export function labelTimelineStage(stage: string): string {
  return timelineStageLabels[stage] ?? stage;
}

export function labelTimelineStatus(status: string): string {
  return timelineStatusLabels[status] ?? labelStatus(status);
}

export function labelTraceEvent(eventType: string): string {
  return traceEventLabels[eventType] ?? eventType;
}
