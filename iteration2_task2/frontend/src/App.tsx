import { useEffect, useState } from "react";

import { ComparisonPanel } from "./components/ComparisonPanel";
import { TaskForm } from "./components/TaskForm";
import {
  createTask,
  deleteTask,
  fetchComparison,
  fetchEvaluationMetadata,
  fetchTaskResult,
  fetchTasks,
  runTask,
  updateTaskStatus
} from "./services/api";
import { DashboardPage } from "./pages/DashboardPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import type {
  ComparisonResponse,
  EvaluationMetadata,
  EvaluationResult,
  EvaluationTask,
  EvaluationTaskCreatePayload,
  TaskStatus
} from "./types/task";

export default function App() {
  const [tasks, setTasks] = useState<EvaluationTask[]>([]);
  const [metadata, setMetadata] = useState<EvaluationMetadata | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string>();
  const [selectedCompareIds, setSelectedCompareIds] = useState<string[]>([]);
  const [resultMap, setResultMap] = useState<Record<string, EvaluationResult>>({});
  const [comparison, setComparison] = useState<ComparisonResponse>();
  const [error, setError] = useState<string>();

  async function loadTasks() {
    const nextTasks = await fetchTasks();
    setTasks(nextTasks);
    setSelectedTaskId((current) => current ?? nextTasks[0]?.id);
  }

  useEffect(() => {
    Promise.all([loadTasks(), fetchEvaluationMetadata().then(setMetadata)]).catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load")
    );
  }, []);

  useEffect(() => {
    if (!selectedTaskId) {
      return;
    }

    fetchTaskResult(selectedTaskId)
      .then((result) => setResultMap((current) => ({ ...current, [selectedTaskId]: result })))
      .catch(() => undefined);
  }, [selectedTaskId]);

  useEffect(() => {
    if (selectedCompareIds.length === 0) {
      setComparison(undefined);
      return;
    }

    fetchComparison(selectedCompareIds)
      .then(setComparison)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to compare"));
  }, [selectedCompareIds]);

  async function handleCreateTask(payload: EvaluationTaskCreatePayload) {
    const created = await createTask(payload);
    setTasks((current) => [created, ...current]);
    setSelectedTaskId(created.id);
  }

  async function handleRunTask(taskId: string) {
    const result = await runTask(taskId);
    setResultMap((current) => ({ ...current, [taskId]: result }));
    await loadTasks();
    setSelectedTaskId(taskId);
  }

  async function handleChangeStatus(taskId: string, status: TaskStatus) {
    const updated = await updateTaskStatus(taskId, status);
    setTasks((current) => current.map((task) => (task.id === taskId ? updated : task)));
  }

  async function handleDeleteTask(taskId: string) {
    await deleteTask(taskId);
    setTasks((current) => current.filter((task) => task.id !== taskId));
    setSelectedCompareIds((current) => current.filter((id) => id !== taskId));
    setSelectedTaskId((current) => (current === taskId ? undefined : current));
  }

  function handleToggleCompare(taskId: string) {
    setSelectedCompareIds((current) =>
      current.includes(taskId) ? current.filter((id) => id !== taskId) : [...current, taskId]
    );
  }

  const selectedTask = tasks.find((task) => task.id === selectedTaskId);
  const selectedResult = selectedTaskId ? resultMap[selectedTaskId] : undefined;

  if (!metadata) {
    return <div className="loading-screen">Loading platform metadata...</div>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>Agent Evaluation Platform</h1>
        <nav>
          <a href="#dashboard">Tasks</a>
          <a href="#builder">Task Builder</a>
          <a href="#detail">Single Analysis</a>
          <a href="#compare">Comparison</a>
        </nav>
      </aside>
      <main className="content">
        <header className="hero card">
          <div>
            <p className="eyebrow">Iteration 2 / Runnable Scaffold</p>
            <h2>Task management, execution, custom metrics, and comparison are wired end-to-end.</h2>
            <p>
              The current version uses FastAPI in-memory persistence plus simulated evaluation results,
              with clear extension points for Ragas execution and trace-based process evaluation.
            </p>
          </div>
          <div className="hero-tags">
            <span>Result + Process</span>
            <span>Explicit + Judge</span>
            <span>Quality / Safety / Performance</span>
          </div>
        </header>

        {error ? <div className="error-banner">{error}</div> : null}

        <section id="dashboard">
          <DashboardPage
            tasks={tasks}
            selectedTaskId={selectedTaskId}
            selectedCompareIds={selectedCompareIds}
            onSelectTask={setSelectedTaskId}
            onToggleCompare={handleToggleCompare}
            onRunTask={(taskId) => void handleRunTask(taskId)}
            onChangeStatus={(taskId, status) => void handleChangeStatus(taskId, status)}
            onDeleteTask={(taskId) => void handleDeleteTask(taskId)}
          />
        </section>

        <section id="builder">
          <TaskForm metadata={metadata} tasks={tasks} onSubmit={handleCreateTask} />
        </section>

        <section id="detail">
          <TaskDetailPage task={selectedTask} result={selectedResult} />
        </section>

        <section id="compare">
          <ComparisonPanel comparison={comparison} />
        </section>
      </main>
    </div>
  );
}
