import { useEffect, useState } from "react";
import { SettingsModal } from "./components/SettingsModal";
import { DashboardPage } from "./pages/DashboardPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import {
  compareTasks,
  createTask,
  deleteTask,
  fetchOpenAIModels,
  fetchHealth,
  fetchMetadata,
  fetchSettings,
  fetchTasks,
  runTask,
  updateSettings
} from "./services/api";
import type {
  AppSettings,
  AppSettingsUpdate,
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
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);

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
      const [health, taskList, metadataResponse, settingsResponse] = await Promise.all([
        fetchHealth(),
        fetchTasks(),
        fetchMetadata(),
        fetchSettings()
      ]);

      setBackendStatus(health.status === "ok" ? "online" : "offline");
      setTasks(taskList);
      setMetadata(metadataResponse);
      setSettings(settingsResponse);
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

  async function handleSaveSettings(payload: AppSettingsUpdate) {
    const updated = await updateSettings(payload);
    setSettings(updated);
    setBanner("设置已保存到 backend/.env。");
    if (payload.model_name !== undefined) {
      await refreshData(true);
    }
  }

  async function handleLoadModels(): Promise<string[]> {
    try {
      setLoadingModels(true);
      const response = await fetchOpenAIModels();
      setModels(response.models);
      setBanner(`已获取 ${response.models.length} 个模型。`);
      return response.models;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "获取模型列表失败");
      throw error;
    } finally {
      setLoadingModels(false);
    }
  }

  const currentTask = tasks.find((task) => task.id === selectedTaskId) ?? null;
  const completedCount = tasks.filter((task) => task.status === "completed").length;
  const runningCount = tasks.filter((task) => task.status === "running" || task.status === "scheduled").length;
  const failedCount = tasks.filter((task) => task.status === "failed").length;
  const successRate = tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;
  const currentSnapshot = currentTask?.result?.current_state;
  const repoPath = currentSnapshot?.repo_path ?? "暂无本地仓库";
  const currentIteration = currentSnapshot
    ? `${currentSnapshot.iteration_count}/${currentSnapshot.max_iterations}`
    : "-";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="app-mark">G</span>
          <div>
            <p className="eyebrow">GitIssueAssitant</p>
            <h1>Agent Console</h1>
          </div>
        </div>

        <nav>
          <a href="#dashboard">新任务</a>
          <a href="#dashboard">搜索</a>
          <a href="#detail">本地变更</a>
          <a href="#compare">对比结果</a>
        </nav>

        <div className="sidebar-task-list">
          {tasks.map((task) => (
            <button
              key={task.id}
              className={`sidebar-task-item ${task.id === selectedTaskId ? "active" : ""}`}
              type="button"
              onClick={() => setSelectedTaskId(task.id)}
            >
              <span>{task.name}</span>
              <small>{formatTaskStatus(task.status)}</small>
            </button>
          ))}
          {tasks.length === 0 ? (
            <div className="sidebar-empty">还没有任务</div>
          ) : null}
        </div>

        <button className="sidebar-settings" type="button" onClick={() => setSettingsOpen(true)}>设置</button>
      </aside>

      <main className="content">
        <header className="hero">
          <div>
            <h2>{currentTask?.name ?? "Agent 运行与评估台"}</h2>
            <p>{currentTask?.description || "创建任务、查看执行轨迹，确认本地 diff 后再决定是否 push。"}</p>
          </div>

          <div className="hero-actions">
            <span className={`health-pill ${backendStatus}`}>后端：{backendStatus}</span>
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
            settings={settings}
            models={models}
            onCreateTask={handleCreateTask}
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

      <aside className="inspector">
        <div className="inspector-card">
          <div className="inspector-header">
            <h2>环境信息</h2>
            <button type="button" onClick={() => void refreshData()}>刷新</button>
          </div>

          <dl className="inspector-list">
            <div>
              <dt>变更</dt>
              <dd>
                <strong>{tasks.length}</strong>
                <span>任务</span>
              </dd>
            </div>
            <div>
              <dt>本地</dt>
              <dd>{repoPath}</dd>
            </div>
            <div>
              <dt>当前状态</dt>
              <dd>{currentTask ? formatTaskStatus(currentTask.status) : "未选择"}</dd>
            </div>
            <div>
              <dt>执行轮数</dt>
              <dd>{currentIteration}</dd>
            </div>
          </dl>

          <div className="inspector-divider" />

          <dl className="inspector-list compact">
            <div>
              <dt>运行中</dt>
              <dd>{runningCount}</dd>
            </div>
            <div>
              <dt>已完成</dt>
              <dd>{completedCount}</dd>
            </div>
            <div>
              <dt>失败</dt>
              <dd>{failedCount}</dd>
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

          <div className="inspector-divider" />

          <div className="inspector-source">
            <span>来源</span>
            <strong>{currentTask?.config.repo_source ?? "暂无来源"}</strong>
          </div>
        </div>
      </aside>

      <SettingsModal
        open={settingsOpen}
        settings={settings}
        models={models}
        loadingModels={loadingModels}
        onClose={() => setSettingsOpen(false)}
        onSave={handleSaveSettings}
        onLoadModels={handleLoadModels}
      />
    </div>
  );
}
