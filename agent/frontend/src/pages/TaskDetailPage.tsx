import { useEffect, useState } from "react";
import {
  createBadCase,
  createTaskPullRequest,
  fetchTaskDiff,
  fetchTaskMessages,
  pushTaskChanges,
  submitTaskMessage,
  taskReportDownloadUrl
} from "../services/api";
import type {
  EvaluationTask,
  GitDiffResponse,
  GitPullRequestResponse,
  GitPushResponse,
  MetricScore,
  RunMode,
  TaskMessage
} from "../types/task";
import { formatDisplayTime } from "../utils/time";

interface TaskDetailPageProps {
  task: EvaluationTask | null;
  busyTaskId: string | null;
  onRunTask: (taskId: string, mode: RunMode, reset?: boolean) => Promise<void>;
  onTaskChanged?: () => Promise<void>;
  onBadCasesChanged?: () => Promise<void>;
}

function formatMetric(metric: MetricScore): string {
  const rawValue = Number.isInteger(metric.value) ? metric.value.toString() : metric.value.toFixed(2);
  return metric.unit ? `${rawValue} ${metric.unit}` : rawValue;
}

function messageRoleLabel(role: TaskMessage["role"]): string {
  if (role === "user") {
    return "用户";
  }
  if (role === "assistant") {
    return "Agent";
  }
  return "系统";
}

function messageRoleHint(role: TaskMessage["role"]): string {
  if (role === "user") {
    return "补充要求";
  }
  if (role === "assistant") {
    return "历史回复";
  }
  return "系统提示";
}

export function TaskDetailPage({ task, busyTaskId, onRunTask, onTaskChanged, onBadCasesChanged }: TaskDetailPageProps) {
  const [expandedEntries, setExpandedEntries] = useState<Record<string, boolean>>({});
  const [diffInfo, setDiffInfo] = useState<GitDiffResponse | null>(null);
  const [messages, setMessages] = useState<TaskMessage[]>([]);
  const [messageContent, setMessageContent] = useState("");
  const [messageReplan, setMessageReplan] = useState(true);
  const [messageBusy, setMessageBusy] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [gitActionBusy, setGitActionBusy] = useState(false);
  const [gitMessage, setGitMessage] = useState<string | null>(null);
  const [gitError, setGitError] = useState<string | null>(null);
  const [pushResult, setPushResult] = useState<GitPushResponse | null>(null);
  const [pullRequestResult, setPullRequestResult] = useState<GitPullRequestResponse | null>(null);
  const [commitMessage, setCommitMessage] = useState("");

  useEffect(() => {
    setExpandedEntries({});
    setDiffInfo(null);
    setGitMessage(null);
    setGitError(null);
    setPushResult(null);
    setPullRequestResult(null);
    setCommitMessage(task ? `fix: ${task.name}` : "");
    setMessages(task?.result?.messages ?? []);
    setMessageContent("");
    setMessageError(null);
  }, [task?.id]);

  useEffect(() => {
    if (!task) {
      return undefined;
    }
    let cancelled = false;
    fetchTaskMessages(task.id)
      .then((response) => {
        if (!cancelled) {
          setMessages(response.messages);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMessages(task.result?.messages ?? []);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [task?.id, task?.result?.messages]);

  useEffect(() => {
    if (!task || task.status !== "completed") {
      return undefined;
    }

    let cancelled = false;
    setDiffLoading(true);
    setGitError(null);

    fetchTaskDiff(task.id)
      .then((response) => {
        if (!cancelled) {
          setDiffInfo(response);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setGitError(error instanceof Error ? error.message : "加载 Git diff 失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setDiffLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [task?.id, task?.status]);

  async function handleRefreshDiff() {
    if (!task) {
      return;
    }
    try {
      setDiffLoading(true);
      setGitError(null);
      setDiffInfo(await fetchTaskDiff(task.id));
    } catch (error) {
      setGitError(error instanceof Error ? error.message : "刷新 Git diff 失败");
    } finally {
      setDiffLoading(false);
    }
  }

  async function handlePushChanges() {
    if (!task || !diffInfo?.has_changes) {
      return;
    }
    try {
      setGitActionBusy(true);
      setGitError(null);
      setGitMessage(null);
      const result = await pushTaskChanges(task.id, {
        commit_message: commitMessage.trim() || `fix: ${task.name}`
      });
      setPushResult(result);
      setGitMessage(result.commit_hash ? `已提交并推送：${result.commit_hash}` : "已推送");
      await handleRefreshDiff();
      await onTaskChanged?.();
    } catch (error) {
      setGitError(error instanceof Error ? error.message : "Git push 失败");
    } finally {
      setGitActionBusy(false);
    }
  }

  async function handleCreatePullRequest() {
    if (!task || !diffInfo?.has_changes) {
      return;
    }
    try {
      setGitActionBusy(true);
      setGitError(null);
      setGitMessage(null);
      const result = await createTaskPullRequest(task.id, {
        commit_message: commitMessage.trim() || `fix: ${task.name}`,
        title: task.result?.fix_report?.suggested_pr_title || `fix: ${task.name}`,
        body: task.result?.fix_report?.suggested_pr_description || task.result?.fix_report?.markdown || ""
      });
      setPullRequestResult(result);
      setGitMessage(result.pr_url ? `已创建 PR：${result.pr_url}` : "已创建 PR");
      await handleRefreshDiff();
      await onTaskChanged?.();
    } catch (error) {
      setGitError(error instanceof Error ? error.message : "创建 PR 失败");
    } finally {
      setGitActionBusy(false);
    }
  }

  async function handleSubmitMessage() {
    if (!task || !messageContent.trim()) {
      return;
    }
    try {
      setMessageBusy(true);
      setMessageError(null);
      const response = await submitTaskMessage(task.id, {
        content: messageContent.trim(),
        replan: messageReplan
      });
      setMessages(response.messages);
      setMessageContent("");
      await onTaskChanged?.();
    } catch (error) {
      setMessageError(error instanceof Error ? error.message : "发送对话失败");
    } finally {
      setMessageBusy(false);
    }
  }

  async function handleSaveBadCase() {
    if (!task) {
      return;
    }
    try {
      setGitError(null);
      await createBadCase({
        task_id: task.id,
        tags: task.status === "failed" ? ["测试失败未恢复"] : [],
        note: task.result?.summary ?? ""
      });
      setGitMessage("已保存为 Bad Case。");
      await onBadCasesChanged?.();
    } catch (error) {
      setGitError(error instanceof Error ? error.message : "保存 Bad Case 失败");
    }
  }

  if (!task) {
    return (
      <section className="card">
        <div className="empty-state">
          <strong>尚未选中任务</strong>
          <p>创建任务或在列表中选择一项后，这里会显示执行状态和时间线。</p>
        </div>
      </section>
    );
  }

  const result = task.result;
  const snapshot = result?.current_state;
  const isBusy = busyTaskId === task.id;

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>任务详情</h2>
          <p>{task.name}</p>
        </div>
        <div className="action-row">
          <button
            className="secondary-button"
            type="button"
            onClick={() => void handleSaveBadCase()}
            disabled={isBusy}
          >
            保存 Bad Case
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={() => void onRunTask(task.id, "step")}
            disabled={isBusy}
          >
            继续单步
          </button>
          <button
            className="primary-button"
            type="button"
            onClick={() => void onRunTask(task.id, "auto")}
            disabled={isBusy}
          >
            自动执行
          </button>
        </div>
      </div>

      {snapshot ? (
        <div className="context-summary">
          <strong>当前上下文</strong>
          <p>状态：{snapshot.status}，轮数：{snapshot.iteration_count}/{snapshot.max_iterations}</p>
          <p>当前计划：{snapshot.plan.length ? snapshot.plan.join(" / ") : "暂无计划"}</p>
        </div>
      ) : null}

      <section className="conversation-panel">
        <div className="section-header compact">
          <div>
            <h3>多轮对话</h3>
            <p>补充约束后，再点击继续单步或自动执行。</p>
          </div>
        </div>

        <div className="conversation-list" aria-label="多轮对话历史">
          {messages.map((message) => (
            <article key={message.id} className={`conversation-message ${message.role}`}>
              <div className="conversation-avatar" aria-hidden="true">
                {message.role === "assistant" ? "A" : message.role === "user" ? "U" : "S"}
              </div>
              <div className="conversation-bubble">
                <div className="conversation-meta">
                  <span>{messageRoleLabel(message.role)}</span>
                  <small>{messageRoleHint(message.role)}</small>
                </div>
                <p>{message.content}</p>
                {message.replan ? <em>触发重新规划</em> : null}
              </div>
            </article>
          ))}
          {!messages.length ? (
            <div className="conversation-empty">
              <strong>暂无对话历史</strong>
              <p>发送补充要求后，这里会按双方消息展示完整对话记录。</p>
            </div>
          ) : null}
        </div>

        {messageError ? <p className="error-copy">{messageError}</p> : null}
        <div className="conversation-composer">
          <textarea
            rows={3}
            value={messageContent}
            onChange={(event) => setMessageContent(event.target.value)}
            placeholder="例如：根据刚才的测试失败继续修。"
            disabled={messageBusy}
          />
          <div className="conversation-composer-actions">
            <button
              className={`replan-toggle ${messageReplan ? "active" : ""}`}
              type="button"
              aria-pressed={messageReplan}
              onClick={() => setMessageReplan((current) => !current)}
            >
              重新规划
            </button>
            <button
              className="conversation-send-button"
              type="button"
              aria-label="发送补充要求"
              onClick={() => void handleSubmitMessage()}
              disabled={messageBusy || !messageContent.trim()}
            >
              ↑
            </button>
          </div>
        </div>
      </section>

      <div className="score-grid">
        {(result?.metrics ?? []).map((metric) => (
          <article key={metric.name} className="score-card">
            <span>{metric.name}</span>
            <strong>{formatMetric(metric)}</strong>
            <small>{metric.description ?? metric.category}</small>
          </article>
        ))}
        {!(result?.metrics?.length ?? 0) ? (
          <article className="score-card">
            <span>尚未执行</span>
            <strong>-</strong>
            <small>任务启动后这里会出现实时汇总指标。</small>
          </article>
        ) : null}
      </div>

      <div className="detail-grid">
        <article>
          <h3>任务配置</h3>
          <dl className="detail-list">
            <div>
              <dt>仓库来源</dt>
              <dd>{task.config.repo_source}</dd>
            </div>
            <div>
              <dt>Issue 输入</dt>
              <dd>{task.config.issue_input}</dd>
            </div>
            <div>
              <dt>运行模式</dt>
              <dd>{task.config.run_mode}</dd>
            </div>
            <div>
              <dt>最大轮数</dt>
              <dd>{task.config.max_iterations}</dd>
            </div>
            {task.config.model_name ? (
              <div>
                <dt>模型名</dt>
                <dd>{task.config.model_name}</dd>
              </div>
            ) : null}
          </dl>
        </article>

        <article>
          <h3>运行状态</h3>
          <dl className="detail-list">
            <div>
              <dt>任务状态</dt>
              <dd>{task.status}</dd>
            </div>
            <div>
              <dt>线程 ID</dt>
              <dd>{snapshot?.thread_id ?? "-"}</dd>
            </div>
            <div>
              <dt>仓库路径</dt>
              <dd>{snapshot?.repo_path ?? "-"}</dd>
            </div>
            <div>
              <dt>当前轮数</dt>
              <dd>{snapshot ? `${snapshot.iteration_count}/${snapshot.max_iterations}` : "-"}</dd>
            </div>
            <div>
              <dt>开始时间</dt>
              <dd>{result?.started_at ? formatDisplayTime(result.started_at) : "-"}</dd>
            </div>
            <div>
              <dt>结束时间</dt>
              <dd>{result?.finished_at ? formatDisplayTime(result.finished_at) : "-"}</dd>
            </div>
          </dl>
        </article>
      </div>

      {task.status === "completed" ? (
        <section className="git-review-panel">
          <div className="section-header">
            <div>
              <h3>本地修改 Diff</h3>
              <p>Agent 只修改本地 clone。确认 diff 后，可由后端提交并 push 到仓库。</p>
            </div>
            <button
              className="secondary-button"
              type="button"
              onClick={() => void handleRefreshDiff()}
              disabled={diffLoading || gitActionBusy}
            >
              刷新 diff
            </button>
          </div>

          {result?.fix_report ? (
            <div className="git-review-meta">
              <div className="section-header compact">
                <div>
                  <h3>修复报告</h3>
                  <p>{result.fix_report.file_name}</p>
                </div>
                <a
                  className="secondary-button"
                  href={taskReportDownloadUrl(task.id)}
                  download={result.fix_report.file_name}
                >
                  下载报告
                </a>
              </div>
              <pre className="git-output-viewer">{result.fix_report.markdown}</pre>
            </div>
          ) : null}

          {gitError ? <p className="error-copy">{gitError}</p> : null}
          {gitMessage ? <p className="success-copy">{gitMessage}</p> : null}

          {diffInfo ? (
            <div className="git-review-meta">
              <dl className="detail-list">
                <div>
                  <dt>本地仓库</dt>
                  <dd>{diffInfo.repo_path}</dd>
                </div>
                <div>
                  <dt>Git status</dt>
                  <dd>{diffInfo.status || "工作区干净"}</dd>
                </div>
              </dl>
            </div>
          ) : null}

          <pre className="diff-viewer">
            {diffLoading
              ? "正在加载 diff..."
              : diffInfo?.diff || "未检测到可展示的 diff。"}
          </pre>

          <div className="git-push-controls">
            <label>
              <span>Commit message</span>
              <input
                value={commitMessage}
                onChange={(event) => setCommitMessage(event.target.value)}
                placeholder={`fix: ${task.name}`}
                disabled={gitActionBusy}
              />
            </label>
            <button
              className="primary-button"
              type="button"
              onClick={() => void handlePushChanges()}
              disabled={gitActionBusy || diffLoading || !diffInfo?.has_changes}
            >
              确认提交并 Push
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => void handleCreatePullRequest()}
              disabled={gitActionBusy || diffLoading || !diffInfo?.has_changes}
            >
              创建 PR
            </button>
          </div>

          {pushResult?.output ? <pre className="git-output-viewer">{pushResult.output}</pre> : null}
          {pullRequestResult?.output ? <pre className="git-output-viewer">{pullRequestResult.output}</pre> : null}
          {pullRequestResult?.pr_url ? (
            <p className="success-copy">
              <a href={pullRequestResult.pr_url} target="_blank" rel="noreferrer">
                打开 PR
              </a>
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="timeline-panel">
        <div className="section-header">
          <div>
            <h3>执行时间线</h3>
            <p>完整展示 planner、react、tools、reflect 四类节点输出。</p>
          </div>
        </div>

        <div className="timeline-list">
          {(result?.timeline ?? []).map((entry) => {
            const isExpanded = !!expandedEntries[entry.id];

            return (
              <article key={entry.id} className="timeline-item">
                <div className="timeline-meta">
                  <span className="timeline-node">{entry.node}</span>
                  <time>{formatDisplayTime(entry.created_at)}</time>
                </div>

                <div className="timeline-title-row">
                  <strong>{entry.title}</strong>
                  <button
                    className="timeline-toggle-button"
                    type="button"
                    onClick={() =>
                      setExpandedEntries((current) => ({
                        ...current,
                        [entry.id]: !current[entry.id]
                      }))
                    }
                  >
                    {isExpanded ? "收起" : "展开"}
                  </button>
                </div>

                {isExpanded ? (
                  <>
                    {entry.content ? <pre>{entry.content}</pre> : <p className="muted-copy">无文本输出</p>}
                    {entry.tool_calls.length > 0 ? (
                      <div className="tool-call-list">
                        {entry.tool_calls.map((toolCall, index) => (
                          <div key={`${entry.id}-tool-${index}`} className="tool-call-chip">
                            <strong>{toolCall.name}</strong>
                            <code>{JSON.stringify(toolCall.args)}</code>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </>
                ) : (
                  <p className="muted-copy">内容已折叠，点击展开查看详情。</p>
                )}
              </article>
            );
          })}

          {!(result?.timeline?.length ?? 0) ? (
            <div className="empty-state inline">
              <strong>暂无执行轨迹</strong>
              <p>点击任务列表中的“单步”或“自动”开始执行。</p>
            </div>
          ) : null}
        </div>
      </section>
    </section>
  );
}
