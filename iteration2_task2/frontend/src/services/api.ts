import type { EvaluationTask } from "../types/task";

const mockTasks: EvaluationTask[] = [
  {
    id: "eval-001",
    name: "客服 Agent 基线评测",
    description: "验证基础问答效果、时延和安全性。",
    status: "completed",
    createdAt: "2026-04-21 09:00",
    updatedAt: "2026-04-21 10:15",
    config: {
      agentVersion: "v1.3.0",
      dataset: "customer-support-v2",
      evaluationMethods: ["面向结果", "显式指标", "效果维度"],
      metrics: ["answer_correctness", "latency", "safety"],
      strategy: "标准组合策略"
    },
    scores: [
      { name: "任务成功率", value: 86, trend: "up" },
      { name: "平均响应时间", value: 72, trend: "stable" },
      { name: "安全得分", value: 93, trend: "up" }
    ]
  },
  {
    id: "eval-002",
    name: "工具调用链路评测",
    description: "关注 Agent 推理过程与工具调用正确率。",
    status: "running",
    createdAt: "2026-04-22 08:30",
    updatedAt: "2026-04-22 08:45",
    config: {
      agentVersion: "v1.4.0-rc1",
      dataset: "tool-usage-benchmark",
      evaluationMethods: ["面向过程", "模糊指标", "性能"],
      metrics: ["tool_accuracy", "reasoning_quality", "token_usage"],
      strategy: "过程+结果混合策略"
    },
    scores: [
      { name: "工具调用正确率", value: 79, trend: "up" },
      { name: "推理质量", value: 74, trend: "stable" },
      { name: "Token 消耗效率", value: 68, trend: "down" }
    ]
  }
];

export async function fetchTasks(): Promise<EvaluationTask[]> {
  return Promise.resolve(mockTasks);
}
