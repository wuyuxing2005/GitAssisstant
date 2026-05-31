import { useEffect, useState } from "react";
import {
  createBadCase,
  createTaskPullRequest,
  fetchTaskDiff,
  fetchTaskMessages,
  pushTaskChanges,
  submitTaskMessage
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

type PublishDialogMode = "push" | "pr" | null;

function formatMetric(metric: MetricScore): string {
  const rawValue = Number.isInteger(metric.value) ? metric.value.toString() : metric.value.toFixed(2);
  return metric.unit ? `${rawValue} ${metric.unit}` : rawValue;
}

function diffStats(diff: string | undefined): { added: number; removed: number } {
  if (!diff) {
    return { added: 0, removed: 0 };
  }
  return diff.split("\n").reduce(
    (stats, line) => {
      if (line.startsWith("+") && !line.startsWith("+++")) {
        stats.added += 1;
      } else if (line.startsWith("-") && !line.startsWith("---")) {
        stats.removed += 1;
      }
      return stats;
    },
    { added: 0, removed: 0 }
  );
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
  const [diffModalOpen, setDiffModalOpen] = useState(false);
  const [publishDialogMode, setPublishDialogMode] = useState<PublishDialogMode>(null);
  const [prTitle, setPrTitle] = useState("");
  const [prBody, setPrBody] = useState("");

  useEffect(() => {
    setExpandedEntries({});
    setDiffInfo(null);
    setGitMessage(null);
    setGitError(null);
    setPushResult(null);
    setPullRequestResult(null);
    setCommitMessage(task ? `fix: ${task.name}` : "");
    setPrTitle(task ? `fix: ${task.name}` : "");
    setPrBody(task?.result?.fix_report?.suggested_pr_description || task?.result?.fix_report?.markdown || "");
    setDiffModalOpen(false);
    setPublishDialogMode(null);
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
        title: prTitle.trim() || task.result?.fix_report?.suggested_pr_title || `fix: ${task.name}`,
        body: prBody.trim() || task.result?.fix_report?.suggested_pr_description || task.result?.fix_report?.markdown || ""
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

  async function openDiffModal() {
    setDiffModalOpen(true);
    if (task && task.status === "completed" && !diffInfo && !diffLoading) {
      await handleRefreshDiff();
    }
  }

  async function openPublishDialog(mode: Exclude<PublishDialogMode, null>) {
    setPublishDialogMode(mode);
    if (task && task.status === "completed" && !diffInfo && !diffLoading) {
      await handleRefreshDiff();
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
  const canPublish = task.status === "completed";
  const stats = diffStats(diffInfo?.diff);
  const localRepoPath = diffInfo?.repo_path || snapshot?.repo_path || "-";
  const hasChanges = !!diffInfo?.has_changes;

  return (
    <>
    <div className="task-detail-layout">
    <section className="card task-detail-main">
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
    <aside className="task-floating-env" aria-label="当前任务环境信息">
      <div className="floating-env-header">
        <div>
          <span>环境信息</span>
          <strong>{canPublish ? "任务已成功" : "等待成功后发布"}</strong>
        </div>
        <button type="button" onClick={() => void handleRefreshDiff()} disabled={!canPublish || diffLoading}>
          刷新
        </button>
      </div>

      <div className="floating-env-list">
        <button className="floating-env-row" type="button" onClick={() => void openDiffModal()} disabled={!canPublish}>
          <span className="floating-env-icon">±</span>
          <span>变更</span>
          <strong>
            {diffLoading ? "加载中" : hasChanges ? (
              <>
                <span className="diff-added">+{stats.added}</span>
                <span className="diff-removed">-{stats.removed}</span>
              </>
            ) : "无变更"}
          </strong>
        </button>

        <div className="floating-env-row static">
          <span className="floating-env-icon">⌂</span>
          <span>本地</span>
          <strong title={localRepoPath}>{localRepoPath}</strong>
        </div>

        <div className="floating-env-row static">
          <span className="floating-env-icon">⑂</span>
          <span>来源</span>
          <strong title={task.config.repo_source}>{task.config.repo_source}</strong>
        </div>

        <button
          className="floating-env-row"
          type="button"
          onClick={() => void openPublishDialog("push")}
          disabled={!canPublish || diffLoading || !hasChanges}
        >
          <span className="floating-env-icon">↗</span>
          <span>提交或推送</span>
          <strong>{canPublish ? "Push" : "未就绪"}</strong>
        </button>

        <button
          className="floating-env-row"
          type="button"
          onClick={() => void openPublishDialog("pr")}
          disabled={!canPublish || diffLoading || !hasChanges}
        >
          <span className="floating-env-icon">⌁</span>
          <span>Pull Request</span>
          <strong>{pullRequestResult?.pr_url ? "已创建" : "创建 PR"}</strong>
        </button>
      </div>

      {gitError ? <p className="floating-env-error">{gitError}</p> : null}
      {gitMessage ? <p className="floating-env-success">{gitMessage}</p> : null}
    </aside>
    </div>

    {diffModalOpen ? (
      <div className="modal-backdrop" role="presentation" onMouseDown={() => setDiffModalOpen(false)}>
        <section className="settings-modal task-diff-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
          <div className="settings-modal-header">
            <div>
              <h2>代码变更 Diff</h2>
              <p>{localRepoPath}</p>
            </div>
            <button className="modal-close-button" type="button" onClick={() => setDiffModalOpen(false)}>关闭</button>
          </div>
          <div className="task-modal-body">
            <pre className="diff-viewer modal-diff-viewer">
              {diffLoading ? "正在加载 diff..." : diffInfo?.diff || "未检测到可展示的 diff。"}
            </pre>
          </div>
        </section>
      </div>
    ) : null}

    {publishDialogMode ? (
      <div className="modal-backdrop" role="presentation" onMouseDown={() => setPublishDialogMode(null)}>
        <section className="settings-modal publish-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
          <div className="settings-modal-header">
            <div>
              <h2>{publishDialogMode === "push" ? "提交并 Push" : "创建 Pull Request"}</h2>
              <p>确认本地变更后再执行发布操作。</p>
            </div>
            <button className="modal-close-button" type="button" onClick={() => setPublishDialogMode(null)}>关闭</button>
          </div>

          <div className="settings-form">
            <label>
              <span>Commit message</span>
              <input
                value={commitMessage}
                onChange={(event) => setCommitMessage(event.target.value)}
                placeholder={`fix: ${task.name}`}
                disabled={gitActionBusy}
              />
            </label>

            {publishDialogMode === "pr" ? (
              <>
                <label>
                  <span>PR 标题</span>
                  <input
                    value={prTitle}
                    onChange={(event) => setPrTitle(event.target.value)}
                    placeholder={`fix: ${task.name}`}
                    disabled={gitActionBusy}
                  />
                </label>
                <label>
                  <span>PR 描述</span>
                  <textarea
                    rows={7}
                    value={prBody}
                    onChange={(event) => setPrBody(event.target.value)}
                    disabled={gitActionBusy}
                  />
                </label>
              </>
            ) : null}

            <div className="publish-diff-summary">
              <span>变更统计</span>
              <strong><span className="diff-added">+{stats.added}</span> <span className="diff-removed">-{stats.removed}</span></strong>
            </div>

            {pushResult?.output && publishDialogMode === "push" ? <pre className="git-output-viewer">{pushResult.output}</pre> : null}
            {pullRequestResult?.output && publishDialogMode === "pr" ? <pre className="git-output-viewer">{pullRequestResult.output}</pre> : null}
            {pullRequestResult?.pr_url && publishDialogMode === "pr" ? (
              <p className="success-copy">
                <a href={pullRequestResult.pr_url} target="_blank" rel="noreferrer">打开 PR</a>
              </p>
            ) : null}

            <div className="settings-actions">
              <button className="secondary-button" type="button" onClick={() => setPublishDialogMode(null)} disabled={gitActionBusy}>
                取消
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={() => void (publishDialogMode === "push" ? handlePushChanges() : handleCreatePullRequest())}
                disabled={gitActionBusy || diffLoading || !hasChanges}
              >
                {publishDialogMode === "push" ? "确认 Push" : "确认创建 PR"}
              </button>
            </div>
          </div>
        </section>
      </div>
    ) : null}
    </>
  );
}
