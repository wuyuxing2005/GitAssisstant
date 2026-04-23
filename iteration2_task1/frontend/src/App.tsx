import { useEffect, useMemo, useState } from "react";
import { createTask, fetchHealth, fetchTasks, runTask } from "./services/api";
import type { CreateTaskPayload, EvaluationTask, RunMode } from "./types/task";

type AgentStatus = "idle" | "draft" | "ready" | "scheduled" | "running" | "completed" | "failed" | "offline";

interface AgentForm {
  repo: string;
  issue: string;
  targetDir: string;
  model: string;
  maxIterations: number;
  runMode: RunMode;
}

const defaultForm: AgentForm = {
  repo: "",
  issue: "",
  targetDir: "",
  model: "",
  maxIterations: 15,
  runMode: "auto"
};

const flowSteps = [
  { title: "准备上下文", detail: "POST /api/tasks，后端保存仓库、Issue 和运行配置。" },
  { title: "单步运行", detail: "POST /api/tasks/{id}/run，mode=step，对应 agent 的 /run。" },
  { title: "自动求解", detail: "POST /api/tasks/{id}/run，mode=auto，对应 /solve --verbose。" },
  { title: "轮询状态", detail: "GET /api/tasks，持续刷新 plan、工具调用、日志和最终状态。" }
];

const commandHelp = [
  { command: "POST /api/tasks", note: "创建真实 agent 任务，初始化仓库和 Issue 配置" },
  { command: "POST /api/tasks/{id}/run", note: "触发单步或自动执行，后端调用 orchestrator" },
  { command: "GET /api/tasks", note: "轮询任务状态、运行快照、时间线和工具输出" },
  { command: "GET /health", note: "检测本地 FastAPI bridge 是否在线" }
];

function quoteShell(value: string): string {
  if (!value.trim()) {
    return "";
  }
  return `"${value.trim().split('"').join('\\"')}"`;
}

function buildCliFallback(form: AgentForm): string[] {
  const commands: string[] = [];
  if (form.model.trim()) {
    commands.push(`$env:MODEL_NAME=${quoteShell(form.model)}`);
  }
  commands.push("python -m gitIssueAssitant");
  if (form.repo.trim()) {
    commands.push(["/repo", quoteShell(form.repo), quoteShell(form.targetDir)].filter(Boolean).join(" "));
  }
  if (form.issue.trim()) {
    commands.push(`/issue ${quoteShell(form.issue)}`);
  }
  commands.push(form.runMode === "auto" ? "/solve --verbose" : "/run");
  commands.push("/status");
  return commands;
}

function taskPayload(form: AgentForm): CreateTaskPayload {
  return {
    name: form.issue.trim().slice(0, 42) || "Git Issue 修复任务",
    description: "由 Web 操控台创建并驱动的 gitIssueAssitant 任务。",
    auto_start: false,
    config: {
      repo_source: form.repo.trim(),
      issue_input: form.issue.trim(),
      target_dir: form.targetDir.trim() || null,
      model_name: form.model.trim() || null,
      max_iterations: form.maxIterations,
      run_mode: form.runMode
    }
  };
}

function statusFromTask(task: EvaluationTask | null, backendOnline: boolean): AgentStatus {
  if (!backendOnline) {
    return "offline";
  }
  if (!task) {
    return "idle";
  }
  return task.status;
}

export default function App() {
  const [form, setForm] = useState<AgentForm>(defaultForm);
  const [currentTask, setCurrentTask] = useState<EvaluationTask | null>(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastAction, setLastAction] = useState("等待连接 backend。");
  const commands = useMemo(() => buildCliFallback(form), [form]);
  const isConfigured = Boolean(form.repo.trim() && form.issue.trim());
  const status = statusFromTask(currentTask, backendOnline);
  const snapshot = currentTask?.result?.current_state;
  const timeline = currentTask?.result?.timeline ?? [];

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (currentTask?.status !== "running" && currentTask?.status !== "scheduled") {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void refresh(currentTask.id);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [currentTask?.id, currentTask?.status]);

  async function refresh(preferredTaskId = currentTask?.id) {
    try {
      const [health, tasks] = await Promise.all([fetchHealth(), fetchTasks()]);
      setBackendOnline(health.status === "ok");
      const selected = tasks.find((task) => task.id === preferredTaskId) ?? tasks[0] ?? null;
      setCurrentTask(selected);
      setLastAction(selected ? `已同步任务 ${selected.id}。` : "backend 在线，暂无任务。");
    } catch (error) {
      setBackendOnline(false);
      setLastAction(error instanceof Error ? error.message : "backend 连接失败。");
    }
  }

  async function ensureTask() {
    if (!isConfigured) {
      throw new Error("请先填写仓库路径和 Issue。");
    }
    if (currentTask && currentTask.config.repo_source === form.repo.trim() && currentTask.config.issue_input === form.issue.trim()) {
      return currentTask;
    }
    const created = await createTask(taskPayload(form));
    setCurrentTask(created);
    return created;
  }

  async function prepareContext() {
    try {
      setBusy(true);
      const task = await ensureTask();
      setLastAction(`任务 ${task.id} 已创建，等待执行。`);
      await refresh(task.id);
    } catch (error) {
      setLastAction(error instanceof Error ? error.message : "创建任务失败。");
    } finally {
      setBusy(false);
    }
  }

  async function execute(mode: RunMode, reset = false) {
    try {
      setBusy(true);
      const task = await ensureTask();
      const updated = await runTask(task.id, { mode, reset });
      setCurrentTask(updated);
      setLastAction(mode === "auto" ? "已触发自动求解，正在轮询状态。" : "已触发单步运行。");
      await refresh(updated.id);
    } catch (error) {
      setLastAction(error instanceof Error ? error.message : "执行失败。");
    } finally {
      setBusy(false);
    }
  }

  async function copyCommands() {
    try {
      await navigator.clipboard.writeText(commands.join("\n"));
      setLastAction("已复制 CLI 兜底指令。");
    } catch {
      setLastAction("浏览器未允许剪贴板，请手动复制右侧指令。");
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">GitIssueAssitant</p>
          <h1>Agent 操控台</h1>
          <p className="sidebar-copy">
            前端按钮通过现有 FastAPI backend 与 agent 通信；backend 再调用 SessionManager 和 Orchestrator。
          </p>
        </div>
        <nav>
          <a href="#control">任务控制</a>
          <a href="#commands">通信方式</a>
          <a href="#timeline">运行轨迹</a>
          <a href="#architecture">架构说明</a>
        </nav>
        <div className={`status-card ${status}`}>
          <span>当前状态</span>
          <strong>{status.toUpperCase()}</strong>
          <p>{lastAction}</p>
        </div>
      </aside>

      <main className="content">
        <section className="hero card">
          <div>
            <p className="eyebrow">Real Agent Bridge</p>
            <h2>按钮现在会真实调用 backend，再由 backend 驱动 agent</h2>
            <p>
              浏览器不能直接启动 Python 进程，所以这里采用现有的本地 FastAPI bridge：
              前端发 HTTP 请求，backend 创建任务、运行图节点并返回状态和时间线。
            </p>
          </div>
          <div className="hero-actions">
            <button className="primary-button" type="button" onClick={prepareContext} disabled={busy}>
              准备上下文
            </button>
            <button className="secondary-button" type="button" onClick={() => void refresh()}>
              刷新状态
            </button>
          </div>
        </section>

        <section id="control" className="control-grid">
          <form className="card control-panel" onSubmit={(event) => event.preventDefault()}>
            <div className="section-header">
              <div>
                <p className="eyebrow">Control</p>
                <h2>任务参数</h2>
              </div>
              <span className={backendOnline ? "pill ready" : "pill"}>{backendOnline ? "backend 在线" : "backend 离线"}</span>
            </div>

            <label>
              <span>仓库路径 / Git URL</span>
              <input
                value={form.repo}
                onChange={(event) => setForm((current) => ({ ...current, repo: event.target.value }))}
                placeholder="C:\\repos\\demo 或 https://github.com/org/repo.git"
              />
            </label>
            <label>
              <span>Issue 输入</span>
              <textarea
                rows={5}
                value={form.issue}
                onChange={(event) => setForm((current) => ({ ...current, issue: event.target.value }))}
                placeholder="粘贴 issue 描述、#123 或 GitHub issue 链接"
              />
            </label>
            <div className="form-row">
              <label>
                <span>克隆目录名</span>
                <input
                  value={form.targetDir}
                  onChange={(event) => setForm((current) => ({ ...current, targetDir: event.target.value }))}
                  placeholder="可选"
                />
              </label>
              <label>
                <span>模型名</span>
                <input
                  value={form.model}
                  onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
                  placeholder="可选，覆盖 MODEL_NAME"
                />
              </label>
              <label>
                <span>最大轮数</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={form.maxIterations}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, maxIterations: Number(event.target.value) || 15 }))
                  }
                />
              </label>
              <label>
                <span>运行模式</span>
                <select
                  value={form.runMode}
                  onChange={(event) => setForm((current) => ({ ...current, runMode: event.target.value as RunMode }))}
                >
                  <option value="auto">自动求解</option>
                  <option value="step">单步调试</option>
                </select>
              </label>
            </div>
            <div className="action-row">
              <button className="secondary-button" type="button" onClick={() => void execute("step")} disabled={busy}>
                单步运行
              </button>
              <button className="primary-button" type="button" onClick={() => void execute("auto")} disabled={busy}>
                自动求解
              </button>
              <button className="ghost-button" type="button" onClick={() => void execute(form.runMode, true)} disabled={busy}>
                重置重跑
              </button>
            </div>
          </form>

          <section id="commands" className="card command-panel">
            <div className="section-header">
              <div>
                <p className="eyebrow">HTTP Bridge</p>
                <h2>真实通信接口</h2>
              </div>
              <button className="ghost-button" type="button" onClick={copyCommands}>
                复制 CLI 兜底
              </button>
            </div>
            <div className="command-help">
              {commandHelp.map((item) => (
                <article key={item.command}>
                  <code>{item.command}</code>
                  <span>{item.note}</span>
                </article>
              ))}
            </div>
            <pre>{commands.join("\n")}</pre>
          </section>
        </section>

        <section id="timeline" className="card">
          <div className="section-header">
            <div>
              <p className="eyebrow">Run Trace</p>
              <h2>运行轨迹</h2>
            </div>
            <span className="pill ready">{currentTask?.id ?? "尚未创建任务"}</span>
          </div>
          <div className="flow-grid">
            {flowSteps.map((step, index) => (
              <article key={step.title} className="flow-card">
                <span>{String(index + 1).padStart(2, "0")}</span>
                <h3>{step.title}</h3>
                <p>{step.detail}</p>
              </article>
            ))}
          </div>
          <div className="terminal-preview">
            <div className="terminal-header">
              <span />
              <span />
              <span />
              <strong>Agent 状态快照</strong>
            </div>
            <pre>{`📊 任务状态: ${status.toUpperCase()}
📁 仓库: ${snapshot?.repo_path || form.repo || "未设置"}
🧩 Issue: ${snapshot?.issue_description || form.issue || "未设置"}
🔁 轮数: ${snapshot?.iteration_count ?? 0}/${snapshot?.max_iterations ?? form.maxIterations}
💬 最近输出: ${snapshot?.last_message || currentTask?.result?.summary || lastAction}`}</pre>
          </div>
          <div className="trace-list">
            {timeline.slice(-6).map((entry) => (
              <article key={entry.id}>
                <strong>{entry.title}</strong>
                <span>{entry.node}</span>
                <p>{entry.content || "无文本输出"}</p>
              </article>
            ))}
            {timeline.length === 0 ? (
              <article>
                <strong>暂无时间线</strong>
                <span>waiting</span>
                <p>点击“单步运行”或“自动求解”后，backend 会把 planner/react/tools 输出写回这里。</p>
              </article>
            ) : null}
          </div>
        </section>

        <section id="architecture" className="card architecture-card">
          <div>
            <p className="eyebrow">Architecture</p>
            <h2>真实链路是 Frontend → Backend → Agent</h2>
            <p>
              前端按钮不再空转。它们调用 <code>frontend/src/services/api.ts</code> 中的 fetch API；
              backend 的任务服务再创建 runtime handle，最终执行 <code>gitIssueAssitant</code> 的 orchestrator。
            </p>
          </div>
          <div className="architecture-list">
            <article>
              <strong>Frontend</strong>
              <span>表单、按钮、轮询和时间线展示。</span>
            </article>
            <article>
              <strong>Backend</strong>
              <span>HTTP bridge，负责启动和调度 agent 运行。</span>
            </article>
            <article>
              <strong>Agent</strong>
              <span>SessionManager 设置仓库和 Issue，Orchestrator 执行图节点。</span>
            </article>
          </div>
        </section>
      </main>
    </div>
  );
}
