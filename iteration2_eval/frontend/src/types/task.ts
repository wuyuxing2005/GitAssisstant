export type TaskStatus = "draft" | "scheduled" | "running" | "completed" | "failed";

export interface EvaluationConfig {
  agentVersion: string;
  dataset: string;
  evaluationMethods: string[];
  metrics: string[];
  strategy: string;
}

export interface EvaluationScore {
  name: string;
  value: number;
  trend: "up" | "down" | "stable";
}

export interface EvaluationTask {
  id: string;
  name: string;
  description: string;
  status: TaskStatus;
  createdAt: string;
  updatedAt: string;
  config: EvaluationConfig;
  scores: EvaluationScore[];
}
