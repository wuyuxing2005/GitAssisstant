import { useEffect, useRef, useState } from "react";
import {
  commentTaskIssue,
  createTaskPullRequest,
  fetchTaskDiff,
  fetchTaskIssue,
  fetchTaskMessages,
  pushTaskChanges,
  submitTaskMessage,
  updateTaskIssueState
} from "../services/api";
import type {
  EvaluationTask,
  GitDiffResponse,
  GitHubIssueInfo,
  GitPullRequestResponse,
  GitPushResponse,
  RunMode,
  TaskMessage
} from "../types/task";
import { formatDisplayTime } from "../utils/time";
import { isGitHubIssueReference } from "../utils/githubIssue";
import { formatTaskStatus, getEffectiveTaskStatus } from "../utils/taskStatus";

interface TaskDetailPageProps {
  task: EvaluationTask | null;
  busyTaskId: string | null;
  onRunTask: (taskId: string, mode: RunMode, reset?: boolean, allowLocalFallback?: boolean) => Promise<void>;
  onTerminateSandboxTask?: (taskId: string) => Promise<void>;
  cachedIssueInfo?: GitHubIssueInfo | null;
  onIssueInfoChanged?: (taskId: string, issueInfo: GitHubIssueInfo | null) => void;
  onTaskChanged?: () => Promise<void>;
}

type PublishDialogMode = "push" | "pr" | null;
type IssueStateDialogMode = "close" | null;
type ParsedDiffLineType = "add" | "remove" | "context" | "meta";

interface ParsedDiffLine {
  type: ParsedDiffLineType;
  oldLine?: number;
  newLine?: number;
  content: string;
}

interface ParsedDiffHunk {
  header: string;
  lines: ParsedDiffLine[];
}

interface ParsedDiffFile {
  oldPath: string;
  newPath: string;
  displayPath: string;
  added: number;
  removed: number;
  isBinary: boolean;
  hunks: ParsedDiffHunk[];
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

function formatRepoSource(source: string): string {
  const trimmed = source.trim();
  if (!trimmed) {
    return "-";
  }

  const sshMatch = trimmed.match(/^[\w.-]+@[^:]+:(.+)$/);
  if (sshMatch) {
    return sshMatch[1].replace(/\.git$/, "");
  }

  try {
    const url = new URL(trimmed);
    const parts = url.pathname
      .replace(/^\/+|\/+$/g, "")
      .replace(/\.git$/, "")
      .split("/")
      .filter(Boolean);
    if (parts.length >= 2) {
      return parts.slice(-2).join("/");
    }
  } catch {
    // Fall through to path handling below.
  }

  const parts = trimmed
    .replace(/\\/g, "/")
    .replace(/\/+$/g, "")
    .replace(/\.git$/, "")
    .split("/")
    .filter(Boolean);
  return parts.length >= 2 ? parts.slice(-2).join("/") : trimmed.replace(/\.git$/, "");
}

function parseDiffPath(raw: string): string {
  if (!raw || raw === "/dev/null") {
    return raw;
  }
  const withoutPrefix = raw.replace(/^"|"$/g, "");
  return withoutPrefix.replace(/^[ab]\//, "");
}

function parseHunkStarts(header: string): { oldLine: number; newLine: number } {
  const match = header.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
  return {
    oldLine: match ? Number(match[1]) : 0,
    newLine: match ? Number(match[2]) : 0
  };
}

function parseUnifiedDiff(diff: string | undefined): ParsedDiffFile[] {
  if (!diff?.trim()) {
    return [];
  }

  const files: ParsedDiffFile[] = [];
  let currentFile: ParsedDiffFile | null = null;
  let currentHunk: ParsedDiffHunk | null = null;
  let oldLine = 0;
  let newLine = 0;

  for (const rawLine of diff.split("\n")) {
    if (rawLine.startsWith("diff --git ")) {
      const match = rawLine.match(/^diff --git a\/(.+?) b\/(.+)$/);
      currentFile = {
        oldPath: match ? match[1] : "",
        newPath: match ? match[2] : "",
        displayPath: match ? match[2] : rawLine.replace("diff --git ", ""),
        added: 0,
        removed: 0,
        isBinary: false,
        hunks: []
      };
      files.push(currentFile);
      currentHunk = null;
      continue;
    }

    if (!currentFile) {
      continue;
    }

    if (rawLine.startsWith("--- ")) {
      currentFile.oldPath = parseDiffPath(rawLine.slice(4).trim());
      continue;
    }

    if (rawLine.startsWith("+++ ")) {
      currentFile.newPath = parseDiffPath(rawLine.slice(4).trim());
      currentFile.displayPath = currentFile.newPath && currentFile.newPath !== "/dev/null"
        ? currentFile.newPath
        : currentFile.oldPath;
      continue;
    }

    if (rawLine.startsWith("@@ ")) {
      currentHunk = { header: rawLine, lines: [] };
      currentFile.hunks.push(currentHunk);
      const starts = parseHunkStarts(rawLine);
      oldLine = starts.oldLine;
      newLine = starts.newLine;
      continue;
    }

    if (rawLine.startsWith("Binary files ") || rawLine === "GIT binary patch") {
      currentFile.isBinary = true;
      currentHunk = { header: "二进制文件变更", lines: [{ type: "meta", content: rawLine }] };
      currentFile.hunks.push(currentHunk);
      continue;
    }

    if (!currentHunk) {
      if (rawLine.trim()) {
        currentHunk = { header: "文件信息", lines: [] };
        currentFile.hunks.push(currentHunk);
        currentHunk.lines.push({ type: "meta", content: rawLine });
      }
      continue;
    }

    if (rawLine.startsWith("+")) {
      currentHunk.lines.push({ type: "add", newLine, content: rawLine.slice(1) });
      currentFile.added += 1;
      newLine += 1;
    } else if (rawLine.startsWith("-")) {
      currentHunk.lines.push({ type: "remove", oldLine, content: rawLine.slice(1) });
      currentFile.removed += 1;
      oldLine += 1;
    } else if (rawLine.startsWith(" ")) {
      currentHunk.lines.push({ type: "context", oldLine, newLine, content: rawLine.slice(1) });
      oldLine += 1;
      newLine += 1;
    } else if (rawLine.startsWith("\\ No newline")) {
      currentHunk.lines.push({ type: "meta", content: rawLine });
    } else if (rawLine.trim()) {
      currentHunk.lines.push({ type: "meta", content: rawLine });
    }
  }

  return files;
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

function mergeConversationMessages(remoteMessages: TaskMessage[], localMessages: TaskMessage[]): TaskMessage[] {
  const byId = new Map<string, TaskMessage>();
  for (const message of [...remoteMessages, ...localMessages]) {
    byId.set(message.id, message);
  }
  return Array.from(byId.values()).sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
}

function taskHasLiveConversation(task: EvaluationTask | null): boolean {
  return task?.status === "scheduled" || task?.status === "running";
}

function StructuredDiffView({ files }: { files: ParsedDiffFile[] }) {
  const visibleFiles = files.filter((file) => !file.isBinary);
  const hiddenBinaryCount = files.length - visibleFiles.length;

  if (!visibleFiles.length) {
    return (
      <div className="structured-diff-empty">
        未检测到可展示的 diff。
      </div>
    );
  }

  return (
    <div className="structured-diff-view">
      {visibleFiles.map((file, fileIndex) => (
        <article key={`${file.displayPath}-${fileIndex}`} className="structured-diff-file">
          <div className="structured-diff-file-header">
            <strong>{file.displayPath}</strong>
            <span>
              <span className="diff-added">+{file.added}</span>
              <span className="diff-removed">-{file.removed}</span>
            </span>
          </div>

          {file.hunks.map((hunk, hunkIndex) => (
            <div key={`${file.displayPath}-hunk-${hunkIndex}`} className="structured-diff-hunk">
              <div className="structured-diff-hunk-header">{hunk.header}</div>
              {hunk.lines.map((line, lineIndex) => (
                <div key={`${file.displayPath}-${hunkIndex}-${lineIndex}`} className={`structured-diff-line ${line.type}`}>
                  <span className="diff-line-number old">{line.oldLine ?? ""}</span>
                  <span className="diff-line-number new">{line.newLine ?? ""}</span>
                  <code>{line.content || " "}</code>
                </div>
              ))}
            </div>
          ))}
        </article>
      ))}
    </div>
  );
}

export function TaskDetailPage({ task, busyTaskId, onRunTask, onTerminateSandboxTask, cachedIssueInfo, onIssueInfoChanged, onTaskChanged }: TaskDetailPageProps) {
  const conversationListRef = useRef<HTMLDivElement | null>(null);
  const messageTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [diffInfo, setDiffInfo] = useState<GitDiffResponse | null>(null);
  const [messages, setMessages] = useState<TaskMessage[]>([]);
  const [localMessages, setLocalMessages] = useState<TaskMessage[]>([]);
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
  const [conversationPinnedToBottom, setConversationPinnedToBottom] = useState(true);
  const [issueInfo, setIssueInfo] = useState<GitHubIssueInfo | null>(null);
  const [issueLoading, setIssueLoading] = useState(false);
  const [issueBusy, setIssueBusy] = useState(false);
  const [issueError, setIssueError] = useState<string | null>(null);
  const [issueMessage, setIssueMessage] = useState<string | null>(null);
  const [issueCommentDialogOpen, setIssueCommentDialogOpen] = useState(false);
  const [issueStateDialogMode, setIssueStateDialogMode] = useState<IssueStateDialogMode>(null);
  const [issueCommentBody, setIssueCommentBody] = useState("");
  const [issueCloseReason, setIssueCloseReason] = useState<"completed" | "not_planned">("completed");
  const [sandboxDecisionAcknowledged, setSandboxDecisionAcknowledged] = useState(false);
  const taskResultMessages = task?.result?.messages ?? [];
  const latestTaskResultMessage = taskResultMessages[taskResultMessages.length - 1];
  const taskResultMessagesVersion = `${taskResultMessages.length}:${latestTaskResultMessage?.id ?? ""}`;

  useEffect(() => {
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
    setLocalMessages([]);
    setConversationPinnedToBottom(true);
    setMessageContent("");
    setMessageError(null);
    setIssueInfo(cachedIssueInfo ?? null);
    setIssueLoading(false);
    setIssueBusy(false);
    setIssueError(null);
    setIssueMessage(null);
    setIssueCommentDialogOpen(false);
    setIssueStateDialogMode(null);
    setIssueCommentBody(cachedIssueInfo?.default_comment ?? "");
    setIssueCloseReason("completed");
    setSandboxDecisionAcknowledged(false);
  }, [task?.id]);

  useEffect(() => {
    if (task?.result?.current_state?.status !== "SANDBOX_UNAVAILABLE") {
      setSandboxDecisionAcknowledged(false);
    }
  }, [task?.id, task?.result?.current_state?.status]);

  useEffect(() => {
    if (!conversationPinnedToBottom) {
      return;
    }
    const list = conversationListRef.current;
    if (!list) {
      return;
    }
    window.requestAnimationFrame(() => {
      list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
    });
  }, [messages, localMessages, conversationPinnedToBottom]);

  useEffect(() => {
    const textarea = messageTextareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, [messageContent]);

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
  }, [task?.id]);

  useEffect(() => {
    if (!task) {
      return;
    }
    setMessages(taskResultMessages);
  }, [task?.id, taskResultMessagesVersion]);

  useEffect(() => {
    if (!task) {
      return undefined;
    }

    let cancelled = false;
    const refreshMessages = async () => {
      try {
        const response = await fetchTaskMessages(task.id);
        if (!cancelled) {
          setMessages(response.messages);
        }
      } catch {
        // Keep the last known conversation visible during transient polling errors.
      }
    };

    void refreshMessages();
    if (!taskHasLiveConversation(task)) {
      return () => {
        cancelled = true;
      };
    }

    const timer = window.setInterval(() => {
      void refreshMessages();
    }, 1500);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [task?.id, task?.status]);

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

  useEffect(() => {
    if (!task) {
      return undefined;
    }
    if (cachedIssueInfo?.task_id === task.id) {
      setIssueInfo(cachedIssueInfo);
      setIssueCommentBody(cachedIssueInfo.default_comment);
      setIssueLoading(false);
      setIssueError(null);
      return undefined;
    }
    if (!isGitHubIssueReference(task.config.issue_input)) {
      setIssueInfo(null);
      onIssueInfoChanged?.(task.id, null);
      setIssueLoading(false);
      setIssueError(null);
      return undefined;
    }
    let cancelled = false;
    setIssueLoading(true);
    setIssueError(null);

    fetchTaskIssue(task.id)
      .then((response) => {
        if (!cancelled) {
          setIssueInfo(response);
          onIssueInfoChanged?.(task.id, response);
          setIssueCommentBody(response.default_comment);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setIssueInfo(null);
          onIssueInfoChanged?.(task.id, null);
          setIssueError(error instanceof Error ? error.message : "加载 Issue 失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIssueLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [task?.id, cachedIssueInfo, onIssueInfoChanged]);

  async function handleRefreshIssue() {
    if (!task) {
      return;
    }
    try {
      setIssueLoading(true);
      setIssueError(null);
      const response = await fetchTaskIssue(task.id);
      setIssueInfo(response);
      onIssueInfoChanged?.(task.id, response);
      if (!issueCommentDialogOpen) {
        setIssueCommentBody(response.default_comment);
      }
    } catch (error) {
      setIssueInfo(null);
      onIssueInfoChanged?.(task.id, null);
      setIssueError(error instanceof Error ? error.message : "刷新 Issue 失败");
    } finally {
      setIssueLoading(false);
    }
  }

  function buildIssueCommentBody(): string {
    const base = issueInfo?.default_comment || task?.result?.fix_report?.markdown || "";
    const publishLines: string[] = [];
    const prUrl = pullRequestResult?.pr_url || task?.result?.pull_request_url;
    const commitHash = pushResult?.commit_hash || pullRequestResult?.commit_hash || task?.result?.last_commit_hash;
    if (prUrl && !base.includes(prUrl)) {
      publishLines.push(`- PR：${prUrl}`);
    }
    if (commitHash && !base.includes(commitHash)) {
      publishLines.push(`- Commit：${commitHash}`);
    }
    if (!publishLines.length) {
      return base;
    }
    return `${base}\n\n### 发布信息\n${publishLines.join("\n")}`;
  }

  function openIssueCommentDialog() {
    setIssueCommentBody(buildIssueCommentBody());
    setIssueMessage(null);
    setIssueError(null);
    setIssueCommentDialogOpen(true);
  }

  async function handleSubmitIssueComment() {
    if (!task || !issueCommentBody.trim()) {
      return;
    }
    try {
      setIssueBusy(true);
      setIssueError(null);
      const response = await commentTaskIssue(task.id, { body: issueCommentBody.trim() });
      setIssueMessage(response.html_url ? `评论已写回：${response.html_url}` : "评论已写回");
      setIssueCommentDialogOpen(false);
      await handleRefreshIssue();
    } catch (error) {
      setIssueError(error instanceof Error ? error.message : "写回 Issue 评论失败");
    } finally {
      setIssueBusy(false);
    }
  }

  async function handleSubmitIssueState() {
    if (!task || !issueStateDialogMode) {
      return;
    }
    try {
      setIssueBusy(true);
      setIssueError(null);
      const response = await updateTaskIssueState(task.id, {
        state: "closed",
        state_reason: issueCloseReason
      });
      setIssueMessage(`Issue 状态已更新：${response.state}`);
      setIssueStateDialogMode(null);
      await handleRefreshIssue();
    } catch (error) {
      setIssueError(error instanceof Error ? error.message : "更新 Issue 状态失败");
    } finally {
      setIssueBusy(false);
    }
  }

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
      setGitMessage(null);
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
      setConversationPinnedToBottom(true);
      const response = await submitTaskMessage(task.id, {
        content: messageContent.trim(),
        replan: messageReplan
      });
      setMessages(response.messages);
      setMessageContent("");
      await onRunTask(task.id, "auto");
    } catch (error) {
      setMessageError(error instanceof Error ? error.message : "发送对话失败");
    } finally {
      setMessageBusy(false);
    }
  }

  function handleConversationScroll() {
    const list = conversationListRef.current;
    if (!list) {
      return;
    }
    const distanceToBottom = list.scrollHeight - list.scrollTop - list.clientHeight;
    setConversationPinnedToBottom(distanceToBottom < 64);
  }

  async function handleRunLocallyAfterSandboxFailure() {
    if (!task) {
      return;
    }
    setConversationPinnedToBottom(true);
    setSandboxDecisionAcknowledged(true);
    setLocalMessages((current) => [
      ...current,
      {
        id: `${task.id}-local-run-local-${Date.now()}`,
        role: "user",
        content: "选择：Docker 不可用，改为本地执行",
        created_at: new Date().toISOString(),
        replan: false
      }
    ]);
    await onRunTask(task.id, "auto", true, true);
  }

  async function handleTerminateAfterSandboxFailure() {
    if (!task || !onTerminateSandboxTask) {
      return;
    }
    setConversationPinnedToBottom(true);
    setSandboxDecisionAcknowledged(true);
    await onTerminateSandboxTask(task.id);
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
  const executionEnvLabel = snapshot?.sandbox_id ? "Docker 沙箱" : "本地执行";
  const waitingForSandboxDecision = snapshot?.status === "SANDBOX_UNAVAILABLE" && !sandboxDecisionAcknowledged;
  const isBusy = busyTaskId === task.id;
  const canPublish = task.status === "completed";
  const stats = diffStats(diffInfo?.diff);
  const localRepoPath = diffInfo?.repo_path || snapshot?.repo_path || "-";
  const repoSourceLabel = formatRepoSource(task.config.repo_source);
  const hasChanges = !!diffInfo?.has_changes;
  const parsedDiffFiles = parseUnifiedDiff(diffInfo?.diff);
  const displayedMessages = mergeConversationMessages(messages, localMessages);
  const effectiveTaskStatus = getEffectiveTaskStatus(task);
  const issueStateLabel = issueLoading
    ? "加载中"
    : issueInfo
      ? issueInfo.state === "closed"
        ? "已关闭"
        : "进行中"
      : "未关联";
  const canCloseIssue = !!issueInfo && issueInfo.state !== "closed" && task.status === "completed";
  const publishStateLabel =
    effectiveTaskStatus === "completed" && hasChanges
      ? "等待发布"
      : formatTaskStatus(effectiveTaskStatus);

  return (
    <>
    <div className="task-detail-layout">
    <section className="card task-detail-main">
      <section className="conversation-panel">
        <div className="section-header compact">
          <div>
            <h3>多轮对话</h3>
            <p>发送补充要求后，Agent 会自动继续处理。</p>
          </div>
        </div>

        <div className="conversation-body">
          <div
            ref={conversationListRef}
            className="conversation-list"
            aria-label="多轮对话历史"
            onScroll={handleConversationScroll}
          >
            {displayedMessages.map((message) => (
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
            {!displayedMessages.length ? (
              <div className="conversation-empty">
                <strong>暂无对话历史</strong>
                <p>发送补充要求后，这里会按双方消息展示完整对话记录。</p>
              </div>
            ) : null}
          </div>

          {waitingForSandboxDecision ? (
            <div className="sandbox-decision-card" role="status">
              <strong>Docker 沙箱不可用</strong>
              <p>请选择继续在本地环境执行，或直接终止该任务。</p>
              <div>
                <button type="button" onClick={() => void handleRunLocallyAfterSandboxFailure()} disabled={isBusy}>
                  本地执行
                </button>
                <button type="button" onClick={() => void handleTerminateAfterSandboxFailure()} disabled={isBusy || !onTerminateSandboxTask}>
                  终止任务
                </button>
              </div>
            </div>
          ) : null}

          {messageError ? <p className="error-copy">{messageError}</p> : null}
          <div className="conversation-composer">
            <textarea
              ref={messageTextareaRef}
              rows={1}
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
        </div>
      </section>

    </section>
    <aside className="task-floating-env" aria-label="当前任务环境信息">
      <div className="floating-env-header">
        <div>
          <span>环境信息</span>
          <strong className={task.status === "failed" ? "failed" : ""}>{publishStateLabel}</strong>
        </div>
        <button type="button" onClick={() => void handleRefreshDiff()} disabled={!canPublish || diffLoading}>
          刷新
        </button>
      </div>

      <div className="floating-env-list">
        <button className="floating-env-row" type="button" onClick={() => void openDiffModal()} disabled={!canPublish}>
          <span className="floating-env-icon">±</span>
          <span>变更</span>
          <strong className="floating-diff-stats">
            {diffLoading ? "加载中" : hasChanges ? (
              <>
                <span className="diff-added">+{stats.added}</span>
                <span className="diff-removed">-{stats.removed}</span>
              </>
            ) : "无变更"}
          </strong>
        </button>

        <div className="floating-env-row static">
          <span className="floating-env-icon">#</span>
          <span>轮数</span>
          <strong>{snapshot ? snapshot.iteration_count : "-"}</strong>
        </div>

        <div className="floating-env-row static">
          <span className="floating-env-icon">⑂</span>
          <span>来源</span>
          <strong title={task.config.repo_source}>{repoSourceLabel}</strong>
        </div>

        <div className="floating-env-row static">
          <span className="floating-env-icon">□</span>
          <span>环境</span>
          <strong>{executionEnvLabel}</strong>
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

      <section className="floating-issue-card" aria-label="Issue 状态">
        <div className="floating-issue-header">
          <div>
            <span>Issue 状态</span>
            <strong>{issueStateLabel}</strong>
          </div>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              void handleRefreshIssue();
            }}
            disabled={issueLoading}
          >
            更新
          </button>
        </div>

        {issueInfo ? (
          <div className="issue-action-grid">
            <button type="button" onClick={openIssueCommentDialog} disabled={issueBusy}>
              写回评论
            </button>
            <button type="button" onClick={() => setIssueStateDialogMode("close")} disabled={issueBusy || !canCloseIssue}>
              关闭 Issue
            </button>
          </div>
        ) : null}
      </section>

      {gitError ? <p className="floating-env-error">{gitError}</p> : null}
      {gitMessage ? <p className="floating-env-success">{gitMessage}</p> : null}
      {issueError ? <p className="floating-env-error">{issueError}</p> : null}
      {issueMessage ? <p className="floating-env-success">{issueMessage}</p> : null}
    </aside>
    </div>

    {diffModalOpen ? (
      <div className="modal-backdrop" role="presentation" onMouseDown={() => setDiffModalOpen(false)}>
        <section className="settings-modal task-diff-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
          <div className="settings-modal-header">
            <div>
              <h2>代码变更 Diff</h2>
              <p>{diffInfo?.branch ? `分支：${diffInfo.branch}` : "分支：-" } / {localRepoPath}</p>
            </div>
            <button className="modal-close-button" type="button" onClick={() => setDiffModalOpen(false)}>关闭</button>
          </div>
          <div className="task-modal-body">
            {diffLoading ? (
              <div className="structured-diff-empty">正在加载 diff...</div>
            ) : (
              <StructuredDiffView files={parsedDiffFiles} />
            )}
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

    {issueCommentDialogOpen ? (
      <div className="modal-backdrop" role="presentation" onMouseDown={() => setIssueCommentDialogOpen(false)}>
        <section className="settings-modal issue-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
          <div className="settings-modal-header">
            <div>
              <h2>写回 Issue 评论</h2>
              <p>确认后才会向 GitHub Issue 写入评论。</p>
            </div>
            <button className="modal-close-button" type="button" onClick={() => setIssueCommentDialogOpen(false)}>关闭</button>
          </div>
          <div className="settings-form">
            <label>
              <span>评论内容</span>
              <textarea
                className="issue-comment-textarea"
                rows={14}
                value={issueCommentBody}
                onChange={(event) => setIssueCommentBody(event.target.value)}
                disabled={issueBusy}
              />
            </label>
            <div className="settings-actions">
              <button className="secondary-button" type="button" onClick={() => setIssueCommentDialogOpen(false)} disabled={issueBusy}>
                取消
              </button>
              <button className="primary-button" type="button" onClick={() => void handleSubmitIssueComment()} disabled={issueBusy || !issueCommentBody.trim()}>
                确认写回
              </button>
            </div>
          </div>
        </section>
      </div>
    ) : null}

    {issueStateDialogMode ? (
      <div className="modal-backdrop" role="presentation" onMouseDown={() => setIssueStateDialogMode(null)}>
        <section className="settings-modal issue-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
          <div className="settings-modal-header">
            <div>
              <h2>关闭 Issue</h2>
              <p>确认后才会修改 GitHub Issue 状态。</p>
            </div>
            <button className="modal-close-button" type="button" onClick={() => setIssueStateDialogMode(null)}>关闭</button>
          </div>
          <div className="settings-form">
            <label>
              <span>关闭原因</span>
              <select
                value={issueCloseReason}
                onChange={(event) => setIssueCloseReason(event.target.value as "completed" | "not_planned")}
                disabled={issueBusy}
              >
                <option value="completed">completed</option>
                <option value="not_planned">not_planned</option>
              </select>
            </label>
            <div className="settings-actions">
              <button className="secondary-button" type="button" onClick={() => setIssueStateDialogMode(null)} disabled={issueBusy}>
                取消
              </button>
              <button className="primary-button" type="button" onClick={() => void handleSubmitIssueState()} disabled={issueBusy}>
                确认更新
              </button>
            </div>
          </div>
        </section>
      </div>
    ) : null}
    </>
  );
}
