import { useEffect, useState } from "react";
import { DashboardPage } from "./pages/DashboardPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import { fetchTasks } from "./services/api";
import type { EvaluationTask } from "./types/task";

export default function App() {
  const [tasks, setTasks] = useState<EvaluationTask[]>([]);

  useEffect(() => {
    fetchTasks().then(setTasks);
  }, []);

  const currentTask = tasks[0];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>Agent 应用评估平台</h1>
        <nav>
          <a href="#dashboard">任务总览</a>
          <a href="#detail">单次结果</a>
          <a href="#compare">对比分析</a>
          <a href="#settings">指标配置</a>
        </nav>
      </aside>
      <main className="content">
        <header className="hero card">
          <div>
            <p className="eyebrow">Iteration 2 / 项目骨架</p>
            <h2>前后端分离的 Agent 评估平台初始化完成</h2>
            <p>
              当前前端提供任务管理、单次结果展示、对比分析与扩展能力的页面骨架。
            </p>
          </div>
          <button className="primary-button">配置新的评测策略</button>
        </header>
        <section id="dashboard">
          <DashboardPage tasks={tasks} />
        </section>
        {currentTask ? (
          <section id="detail">
            <TaskDetailPage task={currentTask} />
          </section>
        ) : null}
      </main>
    </div>
  );
}
