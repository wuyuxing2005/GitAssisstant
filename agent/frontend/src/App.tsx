import { useEffect, useState } from "react";
import { DashboardPage } from "./pages/DashboardPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import {
  compareTasks,
  createTask,
  deleteTask,
  fetchHealth,
  fetchMetadata,
  fetchTasks,
  runTask
} from "./services/api";
import type {
  ComparisonResponse,
  CreateTaskPayload,
  EvaluationMetadataResponse,
  EvaluationTask,
  TaskStatus,
  RunMode
} from "./types/task";

function formatTaskStatus(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    draft: "草稿",
    scheduled: "排队中",
    running: "执行中",
    completed: "已完成",
    failed: "失败"
  };

  return labels[status];
}

export default function App() {
  const [tasks, setTasks] = useState<EvaluationTask[]>([]);
  const [metadata, setMetadata] = useState<EvaluationMetadataResponse | null>(null);
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<"loading" | "online" | "offline">("loading");

  useEffect(() => {
    void refreshData();
  }, []);

  useEffect(() => {
    const hasActiveTask = tasks.some((task) => task.status === "running" || task.status === "scheduled");
    if (!hasActiveTask) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      void refreshData(true);
    }, 3000);

    return () => window.clearInterval(timer);
  }, [tasks]);

  async function refreshData(keepBanner = false) {
    try {
      setErrorMessage(null);
      const [health, taskList, metadataResponse] = await Promise.all([
        fetchHealth(),
        fetchTasks(),
        fetchMetadata()
      ]);

      setBackendStatus(health.status === "ok" ? "online" : "offline");
      setTasks(taskList);
      setMetadata(metadataResponse);
      setSelectedTaskId((current) => {
        if (current && taskList.some((task) => task.id === current)) {
          return current;
        }
        return taskList[0]?.id ?? null;
      });

      if (taskList.length > 0) {
        const comparisonResponse = await compareTasks(taskList.map((task) => task.id));
        setComparison(comparisonResponse);
      } else {
        setComparison(null);
      }

      if (!keepBanner) {
        setBanner(null);
      }
    } catch (error) {
      setBackendStatus("offline");
      setErrorMessage(error instanceof Error ? error.message : "加载数据失败");
    }
  }

  async function handleCreateTask(payload: CreateTaskPayload) {
    try {
      setBusyTaskId("create");
      const task = await createTask(payload);
      setSelectedTaskId(task.id);
      setBanner(payload.auto_start ? "任务已创建并开始执行。" : "任务创建成功。");
      await refreshData(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "创建任务失败");
      throw error;
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleRunTask(taskId: string, mode: RunMode, reset = false) {
    try {
      setBusyTaskId(taskId);
      setSelectedTaskId(taskId);
      await runTask(taskId, { mode, reset });
      setBanner(reset ? "任务已重置并重新调度。" : `任务已按 ${mode} 模式触发。`);
      await refreshData(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "执行任务失败");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleDeleteTask(taskId: string) {
    if (!window.confirm("确认删除该任务吗？")) {
      return;
    }

    try {
      setBusyTaskId(taskId);
      await deleteTask(taskId);
      setBanner("任务已删除。");
      await refreshData(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "删除任务失败");
    } finally {
      setBusyTaskId(null);
    }
  }

  const currentTask = tasks.find((task) => task.id === selectedTaskId) ?? null;
  const completedCount = tasks.filter((task) => task.status === "completed").length;
  const successRate = tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <p className="eyebrow">GitIssueAssitant Console</p>
          <h1>Agent 运行与评估台</h1>
        </div>

        <nav>
          <a href="#dashboard">任务总览</a>
          <a href="#detail">任务详情</a>
          <a href="#compare">横向对比</a>
        </nav>

        <div className="sidebar-panel">
          <span className={`health-pill ${backendStatus}`}>后端：{backendStatus}</span>
          <div className="sidebar-current-task">
            <span className="sidebar-current-task-label">当前任务状态</span>
            <strong>{currentTask?.name ?? "未选择任务"}</strong>
            <span className={`sidebar-task-status ${currentTask?.status ?? "draft"}`}>
              {currentTask ? formatTaskStatus(currentTask.status) : "未开始"}
            </span>
          </div>
          <dl className="sidebar-stats">
            <div>
              <dt>任务数</dt>
              <dd>{tasks.length}</dd>
            </div>
            <div>
              <dt>完成率</dt>
              <dd>{successRate}%</dd>
            </div>
            <div>
              <dt>工具数</dt>
              <dd>{metadata?.builtin_tools.length ?? 0}</dd>
            </div>
          </dl>
        </div>
      </aside>

      <main className="content">
        <header className="hero card">
          <div>
            <p className="eyebrow">Iteration 2 / GitHub Issue Repair Agent</p>
            <h2>把 GitIssueAssitant 封装成可视化任务平台</h2>
            <p>这里直接管理仓库、Issue、执行模式和运行轨迹，前端展示的状态全部来自后端真实接口。</p>
          </div>

          <div className="hero-actions">
            <div className="hero-highlight">
              <span>当前选中</span>
              <strong>{currentTask?.name ?? "未选择任务"}</strong>
            </div>
            <button className="primary-button" type="button" onClick={() => void refreshData()}>
              刷新数据
            </button>
          </div>
        </header>

        {banner ? <div className="banner success">{banner}</div> : null}
        {errorMessage ? <div className="banner error">{errorMessage}</div> : null}

        <section id="dashboard">
          <DashboardPage
            tasks={tasks}
            comparison={comparison}
            selectedTaskId={selectedTaskId}
            busyTaskId={busyTaskId}
            onSelectTask={setSelectedTaskId}
            onCreateTask={handleCreateTask}
            onRunTask={handleRunTask}
            onDeleteTask={handleDeleteTask}
          />
        </section>

        <section id="detail">
          <TaskDetailPage
            task={currentTask}
            busyTaskId={busyTaskId}
            onRunTask={handleRunTask}
            onTaskChanged={() => refreshData(true)}
          />
        </section>
      </main>
    </div>
  );
}
