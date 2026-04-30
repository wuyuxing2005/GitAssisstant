import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  PlusSquare,
  Search,
  Scale,
  Files,
  Zap,
  CheckCircle,
  XCircle,
  Info
} from "lucide-react";

import { ComparisonPanel } from "./components/ComparisonPanel";
import { TaskForm } from "./components/TaskForm";
import {
  createTask,
  deleteTask,
  fetchComparison,
  fetchEvaluationMetadata,
  fetchTaskResult,
  fetchTasks,
  runTask
} from "./services/api";
import { DashboardPage } from "./pages/DashboardPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import type {
  ComparisonResponse,
  EvaluationMetadata,
  EvaluationResult,
  EvaluationTask,
  EvaluationTaskCreatePayload
} from "./types/task";

type ActivePage = "dashboard" | "builder" | "detail" | "compare" | "datasets";

interface NavItem {
  id: ActivePage;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: "layout-dashboard" },
  { id: "builder", label: "Task Builder", icon: "plus-square" },
  { id: "detail", label: "Analysis", icon: "search" },
  { id: "compare", label: "Comparison", icon: "scale" },
  { id: "datasets", label: "Datasets", icon: "files" },
];

export default function App() {
  const [tasks, setTasks] = useState<EvaluationTask[]>([]);
  const [metadata, setMetadata] = useState<EvaluationMetadata | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string>();
  const [selectedCompareIds, setSelectedCompareIds] = useState<string[]>([]);
  const [resultMap, setResultMap] = useState<Record<string, EvaluationResult>>({});
  const [comparison, setComparison] = useState<ComparisonResponse>();
  const [error, setError] = useState<string>();
  const [datasetKey, setDatasetKey] = useState(0);
  const [runningTaskId, setRunningTaskId] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [activePage, setActivePage] = useState<ActivePage>("dashboard");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [toasts, setToasts] = useState<Array<{ id: string; message: string; type: "success" | "error" | "info" }>>([]);

  // 添加 toast 通知
  const addToast = (message: string, type: "success" | "error" | "info" = "info") => {
    const id = Date.now().toString();
    const iconMap = {
      success: <CheckCircle size={18} />,
      error: <XCircle size={18} />,
      info: <Info size={18} />
    };
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  async function loadTasks() {
    const nextTasks = await fetchTasks();
    setTasks(nextTasks);
    setSelectedTaskId((current) => current ?? nextTasks[0]?.id);
  }

  useEffect(() => {
    Promise.all([loadTasks(), fetchEvaluationMetadata().then(setMetadata)]).catch((err) => {
      const errorMsg = err instanceof Error ? err.message : "Failed to load";
      setError(errorMsg);
      addToast(errorMsg, "error");
    });
  }, []);

  useEffect(() => {
    if (datasetKey > 0) {
      fetchEvaluationMetadata().then(setMetadata).catch((err) => {
        const errorMsg = err instanceof Error ? err.message : "Failed to refresh metadata";
        addToast(errorMsg, "error");
      });
    }
  }, [datasetKey]);

  useEffect(() => {
    if (!selectedTaskId) {
      return;
    }

    fetchTaskResult(selectedTaskId)
      .then((result) => {
        setResultMap((current) => ({ ...current, [selectedTaskId]: result }));
      })
      .catch(() => {
        // Silent fail for result loading
      });
  }, [selectedTaskId]);

  useEffect(() => {
    if (selectedCompareIds.length === 0) {
      setComparison(undefined);
      return;
    }

    fetchComparison(selectedCompareIds)
      .then(setComparison)
      .catch((err) => {
        const errorMsg = err instanceof Error ? err.message : "Failed to compare";
        setError(errorMsg);
        addToast(errorMsg, "error");
      });
  }, [selectedCompareIds]);

  async function handleCreateTask(payload: EvaluationTaskCreatePayload) {
    try {
      const created = await createTask(payload);
      setTasks((current) => [created, ...current]);
      setSelectedTaskId(created.id);
      setDatasetKey((key) => key + 1);
      addToast("Task created successfully", "success");
      setActivePage("dashboard");
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Failed to create task";
      addToast(errorMsg, "error");
    }
  }

  async function handleRunTask(taskId: string) {
    setRunningTaskId(taskId);
    setRunError(null);
    try {
      const result = await runTask(taskId);
      setResultMap((current) => ({ ...current, [taskId]: result }));
      await loadTasks();
      setSelectedTaskId(taskId);
      addToast("Task completed successfully", "success");
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Failed to run task";
      setRunError(errorMsg);
      addToast(errorMsg, "error");
      console.error("Run task error:", err);
    } finally {
      setRunningTaskId(null);
    }
  }

  // 定时轮询运行中的任务状态
  useEffect(() => {
    const hasRunningTask = tasks.some((t) => t.status === "running");

    if (!hasRunningTask && !runningTaskId) {
      return;
    }

    const pollInterval = setInterval(async () => {
      const currentTasks = await fetchTasks();

      const tasksChanged = tasks.length !== currentTasks.length ||
        tasks.some((t, i) => t.status !== currentTasks[i]?.status);

      if (tasksChanged) {
        setTasks(currentTasks);

        // 检查是否有任务刚完成
        const completedTask = currentTasks.find(
          (t, i) => tasks[i]?.status === "running" && t.status === "completed"
        );
        if (completedTask) {
          addToast(`Task "${completedTask.name}" completed`, "success");
        }
      }

      if (runningTaskId) {
        const targetTask = currentTasks.find((t) => t.id === runningTaskId);
        if (targetTask && targetTask.status !== "running") {
          setRunningTaskId(null);
        }
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [tasks, runningTaskId]);

  async function handleDeleteTask(taskId: string) {
    try {
      await deleteTask(taskId);
      setTasks((current) => current.filter((task) => task.id !== taskId));
      setSelectedCompareIds((current) => current.filter((id) => id !== taskId));
      setSelectedTaskId((current) => (current === taskId ? undefined : current));
      addToast("Task deleted successfully", "success");
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Failed to delete task";
      addToast(errorMsg, "error");
    }
  }

  function handleToggleCompare(taskId: string) {
    setSelectedCompareIds((current) =>
      current.includes(taskId) ? current.filter((id) => id !== taskId) : [...current, taskId]
    );
  }

  const selectedTask = tasks.find((task) => task.id === selectedTaskId);
  const selectedResult = selectedTaskId ? resultMap[selectedTaskId] : undefined;

  if (!metadata) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner-large">
          <div className="spinner"></div>
          <p>Loading platform...</p>
        </div>
      </div>
    );
  }

  const renderPage = () => {
    switch (activePage) {
      case "dashboard":
        return (
          <DashboardPage
            tasks={tasks}
            selectedTaskId={selectedTaskId}
            selectedCompareIds={selectedCompareIds}
            onSelectTask={(id) => {
              setSelectedTaskId(id);
              setActivePage("detail");
            }}
            onToggleCompare={handleToggleCompare}
            onRunTask={(taskId) => void handleRunTask(taskId)}
            onDeleteTask={(taskId) => void handleDeleteTask(taskId)}
            runningTaskId={runningTaskId}
            runError={runError}
          />
        );
      case "builder":
        return <TaskForm metadata={metadata} tasks={tasks} onSubmit={handleCreateTask} datasetRefreshKey={datasetKey} />;
      case "detail":
        return <TaskDetailPage task={selectedTask} result={selectedResult} />;
      case "compare":
        return <ComparisonPanel comparison={comparison} />;
      case "datasets":
        return <DatasetsPage key={datasetKey} onDatasetUpdated={() => setDatasetKey((key) => key + 1)} />;
      default:
        return null;
    }
  };

  return (
    <div className="app-shell">
      {/* Toast Notifications */}
      <div className="toast-container">
        {toasts.map((toast) => {
          const iconMap = {
            success: <CheckCircle size={18} />,
            error: <XCircle size={18} />,
            info: <Info size={18} />
          };
          return (
            <div key={toast.id} className={`toast toast-${toast.type}`}>
              <span className="toast-icon">{iconMap[toast.type]}</span>
              <span className="toast-message">{toast.message}</span>
            </div>
          );
        })}
      </div>

      {/* Error Banner */}
      {error && (
        <div className="error-banner-fixed">
          <span>{error}</span>
          <button className="btn-close" onClick={() => setError(undefined)}>×</button>
        </div>
      )}

      {/* Sidebar */}
      <aside className={`sidebar ${sidebarCollapsed ? "collapsed" : ""}`}>
        <div className="sidebar-header">
          <div className="logo">
            <span className="logo-icon"><Zap size={24} /></span>
            {!sidebarCollapsed && <span className="logo-text">AgentEval</span>}
          </div>
          <button
            className="collapse-btn"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {sidebarCollapsed ? "→" : "←"}
          </button>
        </div>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => {
            const iconMap: Record<string, JSX.Element> = {
              "layout-dashboard": <LayoutDashboard size={20} />,
              "plus-square": <PlusSquare size={20} />,
              "search": <Search size={20} />,
              "scale": <Scale size={20} />,
              "files": <Files size={20} />
            };
            return (
              <button
                key={item.id}
                className={`nav-item ${activePage === item.id ? "active" : ""}`}
                onClick={() => setActivePage(item.id)}
                title={sidebarCollapsed ? item.label : undefined}
              >
                <span className="nav-icon">{iconMap[item.icon]}</span>
                {!sidebarCollapsed && <span className="nav-label">{item.label}</span>}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          {!sidebarCollapsed && (
            <div className="sidebar-info">
              <p>Version 2.0</p>
              <p className="sidebar-info-muted">Phase 3 Complete</p>
            </div>
          )}
        </div>
      </aside>

      {/* Main Content */}
      <main className="content">
        <header className="content-header">
          <div className="content-title">
            <h1>{NAV_ITEMS.find((item) => item.id === activePage)?.label || "Dashboard"}</h1>
          </div>
          <div className="content-actions">
            <div className="status-indicator">
              <span className="status-dot"></span>
              <span>System Online</span>
            </div>
          </div>
        </header>

        <div className={`page-content ${activePage}`}>
          {renderPage()}
        </div>
      </main>
    </div>
  );
}
