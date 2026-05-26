import { useEffect, useState, type FormEvent } from "react";
import { SummaryCards } from "../components/SummaryCards";
import { TaskTable } from "../components/TaskTable";
import type {
  ComparisonResponse,
  AppSettings,
  CreateTaskPayload,
  EvaluationTask,
  RunMode
} from "../types/task";

interface DashboardPageProps {
  tasks: EvaluationTask[];
  comparison: ComparisonResponse | null;
  selectedTaskId: string | null;
  busyTaskId: string | null;
  settings: AppSettings | null;
  models: string[];
  onSelectTask: (taskId: string) => void;
  onCreateTask: (payload: CreateTaskPayload) => Promise<void>;
  onRunTask: (taskId: string, mode: RunMode, reset?: boolean) => Promise<void>;
  onDeleteTask: (taskId: string) => Promise<void>;
}

function formatMetricValue(value: number): string {
  if (Number.isInteger(value)) {
    return value.toString();
  }
  return value.toFixed(2);
}

function statusText(status: EvaluationTask["status"]): string {
  const mapping: Record<EvaluationTask["status"], string> = {
    draft: "草稿",
    scheduled: "排队中",
    running: "执行中",
    completed: "已完成",
    failed: "失败"
  };

  return mapping[status];
}

export function DashboardPage({
  tasks,
  comparison,
  selectedTaskId,
  busyTaskId,
  settings,
  models,
  onSelectTask,
  onCreateTask,
  onRunTask,
  onDeleteTask
}: DashboardPageProps) {
  const running = tasks.filter((task) => task.status === "running" || task.status === "scheduled").length;
  const completed = tasks.filter((task) => task.status === "completed").length;
  const failed = tasks.filter((task) => task.status === "failed").length;
  const selectedTask = tasks.find((task) => task.id === selectedTaskId) ?? tasks[0] ?? null;
  const previewLogs = selectedTask?.result?.logs_preview ?? [];

  const [formState, setFormState] = useState<CreateTaskPayload>({
    name: "",
    description: "",
    auto_start: true,
    config: {
      repo_source: "",
      issue_input: "",
      target_dir: "",
      model_name: settings?.model_name || models[0] || "",
      max_iterations: 15,
      run_mode: "auto"
    }
  });

  useEffect(() => {
    const nextModel = settings?.model_name || models[0];
    if (!nextModel) {
      return;
    }
    setFormState((current) => {
      if (current.config.model_name) {
        return current;
      }
      return {
        ...current,
        config: { ...current.config, model_name: nextModel }
      };
    });
  }, [settings?.model_name, models]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await onCreateTask({
        ...formState,
        config: {
          ...formState.config,
          target_dir: formState.config.target_dir?.trim() || null,
          model_name: formState.config.model_name?.trim() || null
        }
      });

      setFormState({
        name: "",
        description: "",
        auto_start: true,
        config: {
          repo_source: "",
          issue_input: "",
          target_dir: "",
          model_name: settings?.model_name || models[0] || "",
          max_iterations: 15,
          run_mode: "auto"
        }
      });
    } catch {
      // App already surfaces the error banner.
    }
  }

  return (
    <div className="page-grid">
      <SummaryCards total={tasks.length} running={running} completed={completed} failed={failed} />

      <section className="card composer-card">
        <div className="section-header">
          <div>
            <h2>创建新任务</h2>
            <p>输入仓库地址或本地路径，再给出 Issue 文本、编号或 GitHub issue 链接。</p>
          </div>
        </div>

        <form className="task-form" onSubmit={handleSubmit}>
          <label>
            <span>任务名称</span>
            <input
              required
              value={formState.name}
              onChange={(event) =>
                setFormState((current) => ({ ...current, name: event.target.value }))
              }
              placeholder="例如：修复代码搜索工具路径判断"
            />
          </label>

          <label>
            <span>仓库路径或 Git URL</span>
            <input
              required
              value={formState.config.repo_source}
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  config: { ...current.config, repo_source: event.target.value }
                }))
              }
              placeholder="例如：repos/myproject 或 https://github.com/org/repo.git"
            />
          </label>

          <label>
            <span>Issue 描述 / 编号 / 链接</span>
            <textarea
              required
              rows={4}
              value={formState.config.issue_input}
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  config: { ...current.config, issue_input: event.target.value }
                }))
              }
              placeholder="例如：123 或完整 issue 文本"
            />
          </label>

          <label>
            <span>补充说明</span>
            <textarea
              rows={3}
              value={formState.description}
              onChange={(event) =>
                setFormState((current) => ({ ...current, description: event.target.value }))
              }
              placeholder="记录预期修复范围、限制条件或上下文说明"
            />
          </label>

          <div className="form-row">
            <label>
              <span>克隆到本地目录名</span>
              <input
                value={formState.config.target_dir ?? ""}
                onChange={(event) =>
                  setFormState((current) => ({
                    ...current,
                    config: { ...current.config, target_dir: event.target.value }
                  }))
                }
                placeholder="可选，仅远程仓库需要"
              />
            </label>

            <label>
              <span>模型名</span>
              <select
                required
                value={formState.config.model_name ?? ""}
                onChange={(event) =>
                  setFormState((current) => ({
                    ...current,
                    config: { ...current.config, model_name: event.target.value }
                  }))
                }
              >
                {settings?.model_name ? <option value={settings.model_name}>{settings.model_name}</option> : null}
                {models
                  .filter((model) => model !== settings?.model_name)
                  .map((model) => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                {!settings?.model_name && models.length === 0 ? (
                  <option value="" disabled>请先在设置中导入模型</option>
                ) : null}
              </select>
            </label>

            <label>
              <span>最大轮数</span>
              <input
                type="number"
                min={1}
                max={50}
                value={formState.config.max_iterations}
                onChange={(event) =>
                  setFormState((current) => ({
                    ...current,
                    config: {
                      ...current.config,
                      max_iterations: Number(event.target.value) || 15
                    }
                  }))
                }
              />
            </label>

            <label>
              <span>运行模式</span>
              <select
                value={formState.config.run_mode}
                onChange={(event) =>
                  setFormState((current) => ({
                    ...current,
                    config: {
                      ...current.config,
                      run_mode: event.target.value as RunMode
                    }
                  }))
                }
              >
                <option value="auto">auto</option>
                <option value="step">step</option>
              </select>
            </label>
          </div>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={formState.auto_start}
              onChange={(event) =>
                setFormState((current) => ({ ...current, auto_start: event.target.checked }))
              }
            />
            <span>创建后立即按当前模式执行</span>
          </label>

          <div className="action-row">
            <button className="primary-button" type="submit" disabled={busyTaskId === "create"}>
              创建任务
            </button>
          </div>
        </form>
      </section>

      <TaskTable
        tasks={tasks}
        selectedTaskId={selectedTaskId}
        busyTaskId={busyTaskId}
        onSelectTask={onSelectTask}
        onRunTask={onRunTask}
        onDeleteTask={onDeleteTask}
      />

      <section className="card dashboard-terminal-card">
        <div className="section-header">
          <div>
            <h2>实时日志</h2>
            <p>{selectedTask ? `当前任务：${selectedTask.name}` : "选中任务后这里会显示日志预览。"}</p>
          </div>
        </div>

        <div className="terminal-panel">
          <div className="terminal-header">
            <div className="terminal-actions" aria-hidden="true">
              <span className="terminal-dot terminal-dot-close" />
              <span className="terminal-dot terminal-dot-minimize" />
              <span className="terminal-dot terminal-dot-expand" />
            </div>
            <span className="terminal-title">bash</span>
          </div>

          <div className="terminal-body dashboard-terminal-body">
            {previewLogs.map((logLine, index) => {
              const match = logLine.match(/^(\d{2}:\d{2}:\d{2})(.*)$/);
              const time = match?.[1];
              const message = match?.[2]?.trimStart() ?? logLine;

              return (
                <div key={`${selectedTask?.id ?? "task"}-preview-log-${index}`} className="terminal-line">
                  <span className="terminal-prompt">$</span>
                  <code>
                    {time ? <span className="terminal-time">{time}</span> : null}
                    <span>{message}</span>
                  </code>
                </div>
              );
            })}

            {!previewLogs.length ? (
              <p className="muted-copy terminal-empty">当前任务还没有日志输出。</p>
            ) : null}
          </div>
        </div>
      </section>

      <section id="compare" className="card comparison-panel">
        <div className="section-header">
          <div>
            <h2>任务对比</h2>
            <p>横向比较不同任务的成功情况、迭代轮数、工具使用和测试验证情况。</p>
          </div>
        </div>

        {comparison && comparison.items.length > 0 ? (
          <div className="comparison-grid">
            {comparison.items.map((item) => (
              <article key={item.task_id} className="comparison-card">
                <div className="comparison-card-header">
                  <div>
                    <strong>{item.task_name}</strong>
                    <p>{item.summary}</p>
                  </div>
                  <span className={`status-badge ${item.status}`}>{statusText(item.status)}</span>
                </div>

                <div className="metric-list">
                  {item.scores.map((score) => (
                    <div key={`${item.task_id}-${score.name}`} className="metric-row">
                      <span>{score.name}</span>
                      <strong>
                        {formatMetricValue(score.value)}
                        {score.unit ? ` ${score.unit}` : ""}
                      </strong>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <strong>暂无可对比数据</strong>
            <p>先运行至少一个任务，再查看汇总指标矩阵。</p>
          </div>
        )}
      </section>
    </div>
  );
}
