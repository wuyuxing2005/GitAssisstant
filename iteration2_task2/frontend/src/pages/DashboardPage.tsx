import type { EvaluationTask } from "../types/task";
import { SummaryCards } from "../components/SummaryCards";
import { TaskTable } from "../components/TaskTable";

interface DashboardPageProps {
  tasks: EvaluationTask[];
}

export function DashboardPage({ tasks }: DashboardPageProps) {
  const running = tasks.filter((task) => task.status === "running").length;
  const completed = tasks.filter((task) => task.status === "completed").length;

  return (
    <div className="page-grid">
      <SummaryCards
        total={tasks.length}
        running={running}
        completed={completed}
        customMetrics={6}
      />
      <TaskTable tasks={tasks} />
      <section className="card two-column-panel">
        <div>
          <h2>评测方法能力</h2>
          <ul>
            <li>结果导向 / 过程导向双视角评测</li>
            <li>显式指标 + LLM-as-a-Judge 模糊指标</li>
            <li>效果 / 安全 / 性能多维度分析</li>
            <li>预留 Ragas 与自定义指标接入点</li>
          </ul>
        </div>
        <div>
          <h2>对比分析能力</h2>
          <ul>
            <li>支持任务间横向对比</li>
            <li>支持单次任务细粒度结果展示</li>
            <li>支持组合评估策略编排</li>
            <li>支持后续补充图表组件</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
