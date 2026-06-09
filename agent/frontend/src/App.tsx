import { useCallback, useEffect, useState, type CSSProperties, type MouseEvent, type PointerEvent } from "react";
import { SettingsModal } from "./components/SettingsModal";
import { SkillManager } from "./components/SkillManager";
import { ComparePage } from "./pages/ComparePage";
import { DashboardPage } from "./pages/DashboardPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import { formatTaskStatus, getEffectiveTaskStatus } from "./utils/taskStatus";
import {
  compareTasks,
  createTask,
  deleteTask,
  fetchOpenAIModels,
  fetchHealth,
  fetchSettings,
  fetchSkills,
  fetchTaskIssue,
  fetchTasks,
  runTask,
  terminateSandboxTask,
  updateSettings
} from "./services/api";
import type {
  AppSettings,
  AppSettingsUpdate,
  ComparisonResponse,
  CreateTaskPayload,
  EvaluationTask,
  GitHubIssueInfo,
  SkillRecord,
  RunMode
} from "./types/task";

type PageKey = "new-task" | "detail" | "skills" | "compare";

const DEFAULT_SIDEBAR_WIDTH = 386;
const MIN_SIDEBAR_WIDTH = 260;
const MAX_SIDEBAR_WIDTH = 560;
const SIDEBAR_WIDTH_STORAGE_KEY = "agent-console-sidebar-width";
const CURRENT_PAGE_STORAGE_KEY = "agent-console-current-page";
const SELECTED_TASK_STORAGE_KEY = "agent-console-selected-task-id";

function isPageKey(value: string | null): value is PageKey {
  return value === "new-task" || value === "detail" || value === "skills" || value === "compare";
}

function clampSidebarWidth(value: number): number {
  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, value));
}

function pageTitle(page: PageKey, task: EvaluationTask | null): string {
  if (page === "new-task") {
    return "创建新任务";
  }
  if (page === "detail") {
    return task?.name ?? "任务详情";
  }
  if (page === "skills") {
    return "Skill 管理";
  }
  return "对比结果";
}

export default function App() {
  const [tasks, setTasks] = useState<EvaluationTask[]>([]);
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [skills, setSkills] = useState<SkillRecord[]>([]);
  const [currentPage, setCurrentPage] = useState<PageKey>(() => {
    const stored = window.localStorage.getItem(CURRENT_PAGE_STORAGE_KEY);
    return isPageKey(stored) ? stored : "new-task";
  });
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(() => window.localStorage.getItem(SELECTED_TASK_STORAGE_KEY));
  const [issueInfoCache, setIssueInfoCache] = useState<Record<string, GitHubIssueInfo>>({});
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<"loading" | "online" | "offline">("loading");
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const stored = window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY);
    const parsed = stored ? Number(stored) : DEFAULT_SIDEBAR_WIDTH;
    return Number.isFinite(parsed) ? clampSidebarWidth(parsed) : DEFAULT_SIDEBAR_WIDTH;
  });
  const [resizingSidebar, setResizingSidebar] = useState(false);
  const hasActiveTask = tasks.some((task) => {
    const status = getEffectiveTaskStatus(task);
    return status === "running" || status === "scheduled";
  });

  useEffect(() => {
    void refreshData();
  }, []);

  useEffect(() => {
    window.localStorage.setItem(CURRENT_PAGE_STORAGE_KEY, currentPage);
  }, [currentPage]);

  useEffect(() => {
    if (selectedTaskId) {
      window.localStorage.setItem(SELECTED_TASK_STORAGE_KEY, selectedTaskId);
    } else {
      window.localStorage.removeItem(SELECTED_TASK_STORAGE_KEY);
    }
  }, [selectedTaskId]);

  useEffect(() => {
    if (!hasActiveTask) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      void refreshTaskList(true);
    }, 3000);

    return () => window.clearInterval(timer);
  }, [hasActiveTask]);

  function syncTaskList(taskList: EvaluationTask[]) {
    setTasks(taskList);
    setSelectedTaskId((current) => {
      if (current && taskList.some((task) => task.id === current)) {
        return current;
      }
      const stored = window.localStorage.getItem(SELECTED_TASK_STORAGE_KEY);
      if (stored && taskList.some((task) => task.id === stored)) {
        return stored;
      }
      return taskList[0]?.id ?? null;
    });
  }

  async function refreshTaskList(_keepBanner = false) {
    try {
      setErrorMessage(null);
      const taskList = await fetchTasks();
      setBackendStatus("online");
      syncTaskList(taskList);
    } catch (error) {
      setBackendStatus("offline");
      setErrorMessage(error instanceof Error ? error.message : "鍔犺浇浠诲姟澶辫触");
    }
  }

  async function refreshData(_keepBanner = false) {
    try {
      setErrorMessage(null);
      const [health, taskList, settingsResponse, skillResponse] = await Promise.all([
        fetchHealth(),
        fetchTasks(),
        fetchSettings(),
        fetchSkills()
      ]);

      setBackendStatus(health.status === "ok" ? "online" : "offline");
      syncTaskList(taskList);
      setSettings(settingsResponse);
      setSkills(skillResponse.items);

      if (taskList.length > 0) {
        const comparisonResponse = await compareTasks(taskList.map((task) => task.id));
        setComparison(comparisonResponse);
      } else {
        setComparison(null);
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
      const issueInfo = await fetchTaskIssue(task.id).catch(() => null);
      if (issueInfo) {
        setIssueInfoCache((current) => ({ ...current, [task.id]: issueInfo }));
      }
      setSelectedTaskId(task.id);
      setCurrentPage("detail");
      await refreshData(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "创建任务失败");
      throw error;
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleRunTask(taskId: string, mode: RunMode, reset = false, allowLocalFallback = false) {
    try {
      setBusyTaskId(taskId);
      setSelectedTaskId(taskId);
      setCurrentPage("detail");
      await runTask(taskId, { mode, reset, allow_local_fallback: allowLocalFallback });
      await refreshData(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "执行任务失败");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleTerminateSandboxTask(taskId: string) {
    try {
      setBusyTaskId(taskId);
      setSelectedTaskId(taskId);
      setCurrentPage("detail");
      await terminateSandboxTask(taskId);
      await refreshData(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "终止任务失败");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function handleDeleteTask(taskId: string) {
    const task = tasks.find((item) => item.id === taskId);
    const confirmed = window.confirm(`确定删除任务 "${task?.name ?? taskId}" 吗？此操作不可恢复。`);
    if (!confirmed) {
      return;
    }

    try {
      setBusyTaskId(taskId);
      await deleteTask(taskId);
      setIssueInfoCache((current) => {
        const next = { ...current };
        delete next[taskId];
        return next;
      });
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
    if (payload.model_name !== undefined) {
      await refreshData(true);
    }
  }

  const handleLoadModels = useCallback(async (): Promise<string[]> => {
    try {
      setLoadingModels(true);
      const response = await fetchOpenAIModels();
      setModels(response.models);
      return response.models;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "获取模型列表失败");
      throw error;
    } finally {
      setLoadingModels(false);
    }
  }, []);

  async function handleOpenSettings() {
    try {
      setErrorMessage(null);
      const latestSettings = await fetchSettings();
      setSettings(latestSettings);
      setSettingsOpen(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "加载设置失败");
    }
  }

  function handleNavClick(event: MouseEvent<HTMLAnchorElement>, page: PageKey) {
    event.preventDefault();
    setCurrentPage(page);
  }

  function handleSidebarResizePointerDown(event: PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    setResizingSidebar(true);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const handlePointerMove = (moveEvent: globalThis.PointerEvent) => {
      const nextWidth = clampSidebarWidth(moveEvent.clientX);
      setSidebarWidth(nextWidth);
      window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, nextWidth.toString());
    };

    const handlePointerUp = () => {
      setResizingSidebar(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
  }

  const currentTask = tasks.find((task) => task.id === selectedTaskId) ?? null;
  const currentIssueInfo = currentTask ? issueInfoCache[currentTask.id] ?? null : null;
  const handleIssueInfoChanged = useCallback((taskId: string, issueInfo: GitHubIssueInfo | null) => {
    setIssueInfoCache((current) => {
      if (issueInfo) {
        return { ...current, [taskId]: issueInfo };
      }
      const next = { ...current };
      delete next[taskId];
      return next;
    });
  }, []);

  const appShellStyle = {
    "--sidebar-width": `${sidebarWidth}px`
  } as CSSProperties;

  return (
    <div className={`app-shell ${currentPage === "detail" ? "detail-shell" : ""} ${resizingSidebar ? "resizing-sidebar" : ""}`} style={appShellStyle}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="app-mark">G</span>
          <div>
            <h1>GitIssueAssitant</h1>
          </div>
        </div>

        <nav>
          <a href="#dashboard" onClick={(event) => handleNavClick(event, "new-task")}>新任务</a>
          <a href="#skills" onClick={(event) => handleNavClick(event, "skills")}>Skill</a>
          <a href="#compare" onClick={(event) => handleNavClick(event, "compare")}>对比结果</a>
        </nav>

        <div className="sidebar-task-list">
          {tasks.map((task) => (
            <div
              key={task.id}
              className={`sidebar-task-item ${task.id === selectedTaskId ? "active" : ""}`}
            >
              <button
                className="sidebar-task-select"
                type="button"
                onClick={() => {
                  setSelectedTaskId(task.id);
                  setCurrentPage("detail");
                }}
              >
                <span>{task.name}</span>
                <small>{formatTaskStatus(getEffectiveTaskStatus(task))}</small>
              </button>
              <button
                className="sidebar-task-delete"
                type="button"
                aria-label={`删除任务 ${task.name}`}
                title="删除任务"
                disabled={busyTaskId === task.id}
                onClick={() => void handleDeleteTask(task.id)}
              >
                ×
              </button>
            </div>
          ))}
          {tasks.length === 0 ? (
            <div className="sidebar-empty">还没有任务</div>
          ) : null}
        </div>

        <button className="sidebar-settings" type="button" onClick={() => void handleOpenSettings()}>设置</button>
      </aside>

      <div
        className={`sidebar-resizer ${resizingSidebar ? "active" : ""}`}
        role="separator"
        aria-label="调整左侧导航栏宽度"
        aria-orientation="vertical"
        aria-valuemin={MIN_SIDEBAR_WIDTH}
        aria-valuemax={MAX_SIDEBAR_WIDTH}
        aria-valuenow={sidebarWidth}
        onPointerDown={handleSidebarResizePointerDown}
      />

      <main className="content">
        <header className="hero">
          <div className="hero-title-block">
            <div className="hero-title-row">
              <h2>{pageTitle(currentPage, currentTask)}</h2>
              {currentPage === "detail" && currentIssueInfo ? (
                <div className="hero-issue-summary" aria-label="Issue 标题和内容">
                  <span>Issue #{currentIssueInfo.number}</span>
                  <strong title={currentIssueInfo.title}>{currentIssueInfo.title}</strong>
                  <a href={currentIssueInfo.html_url} target="_blank" rel="noreferrer">打开 GitHub</a>
                </div>
              ) : null}
            </div>
          </div>

          <div className="hero-actions">
            <span className={`health-pill ${backendStatus}`}>后端：{backendStatus}</span>
            <button className="primary-button" type="button" onClick={() => void refreshData()}>
              刷新数据
            </button>
          </div>
        </header>

        {errorMessage ? <div className="banner error">{errorMessage}</div> : null}

        {currentPage === "new-task" ? (
          <DashboardPage
            busyTaskId={busyTaskId}
            settings={settings}
            models={models}
            skills={skills}
            onCreateTask={handleCreateTask}
          />
        ) : null}

        {currentPage === "detail" ? (
          <TaskDetailPage
            task={currentTask}
            busyTaskId={busyTaskId}
            onRunTask={handleRunTask}
            onTerminateSandboxTask={handleTerminateSandboxTask}
            cachedIssueInfo={currentIssueInfo}
            onIssueInfoChanged={handleIssueInfoChanged}
            onTaskChanged={() => refreshData(true)}
          />
        ) : null}

        {currentPage === "skills" ? (
          <SkillManager
            skills={skills}
            onChanged={() => refreshData(true)}
          />
        ) : null}

        {currentPage === "compare" ? (
          <ComparePage tasks={tasks} comparison={comparison} />
        ) : null}
      </main>

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
