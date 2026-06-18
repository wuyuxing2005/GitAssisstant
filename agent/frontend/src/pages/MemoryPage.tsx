import { useEffect, useState, type ReactNode } from "react";
import { clearMemories, deleteMemory, fetchMemories, rebuildMemories } from "../services/api";
import type { LongTermMemoryRecord } from "../types/task";
import { formatDisplayTime } from "../utils/time";

type PendingMemoryDelete =
  | { kind: "memory"; memory: LongTermMemoryRecord }
  | { kind: "clear" };

function repoLabel(source: string): string {
  const normalized = source.replace(/\\/g, "/").replace(/\.git$/, "").replace(/\/+$/, "");
  const parts = normalized.split("/").filter(Boolean);
  return parts.length >= 2 ? parts.slice(-2).join("/") : source;
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length >= 4) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function renderMarkdown(content: string): ReactNode[] {
  const lines = content.split("\n");
  const blocks: ReactNode[] = [];
  let paragraphLines: string[] = [];
  let listItems: string[] = [];
  let index = 0;

  const flushParagraph = () => {
    if (!paragraphLines.length) return;
    blocks.push(<p key={`p-${blocks.length}`}>{renderInlineMarkdown(paragraphLines.join("\n"))}</p>);
    paragraphLines = [];
  };

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(
      <ul key={`ul-${blocks.length}`}>
        {listItems.map((item, itemIndex) => (
          <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
        ))}
      </ul>
    );
    listItems = [];
  };

  while (index < lines.length) {
    const line = lines[index];
    const fenceMatch = line.match(/^```(\S*)\s*$/);
    if (fenceMatch) {
      flushParagraph();
      flushList();
      const language = fenceMatch[1];
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(
        <pre key={`code-${blocks.length}`}>
          <code className={language ? `language-${language}` : undefined}>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      blocks.push(level === 1
        ? <h2 key={`h-${blocks.length}`}>{renderInlineMarkdown(text)}</h2>
        : <h3 key={`h-${blocks.length}`}>{renderInlineMarkdown(text)}</h3>);
      index += 1;
      continue;
    }

    const listMatch = line.match(/^\s*[-*]\s+(.+)$/);
    if (listMatch) {
      flushParagraph();
      listItems.push(listMatch[1]);
      index += 1;
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      index += 1;
      continue;
    }

    flushList();
    paragraphLines.push(line);
    index += 1;
  }

  flushParagraph();
  flushList();
  return blocks;
}

export function MemoryPage() {
  const [memories, setMemories] = useState<LongTermMemoryRecord[]>([]);
  const [expandedMemoryId, setExpandedMemoryId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<PendingMemoryDelete | null>(null);

  async function loadMemories() {
    try {
      setBusy(true);
      setErrorMessage(null);
      const response = await fetchMemories();
      setMemories(response.items);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "加载长期记忆失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void loadMemories();
  }, []);

  async function handleRebuild() {
    try {
      setRebuilding(true);
      setMessage(null);
      setErrorMessage(null);
      const response = await rebuildMemories(20);
      await loadMemories();
      setMessage(`已新增 ${response.count} 条记忆，跳过已有 ${response.skipped_count} 条`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "重建长期记忆失败");
    } finally {
      setRebuilding(false);
    }
  }

  async function handleDelete(memory: LongTermMemoryRecord) {
    try {
      setBusy(true);
      setMessage(null);
      setErrorMessage(null);
      await deleteMemory(memory.id);
      setMemories((current) => current.filter((item) => item.id !== memory.id));
      setExpandedMemoryId((current) => (current === memory.id ? null : current));
      setPendingDelete(null);
      setMessage("已删除该记忆");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "删除长期记忆失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleClear() {
    try {
      setBusy(true);
      setMessage(null);
      setErrorMessage(null);
      const response = await clearMemories();
      setMemories([]);
      setExpandedMemoryId(null);
      setPendingDelete(null);
      setMessage(`已清空 ${response.count} 条记忆`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "清空长期记忆失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="card memory-panel">
        <div className="section-header">
          <div>
            <h2>长期记忆</h2>
            <p>系统会从最近完成或失败的任务中沉淀经验，并在新任务启动时自动注入相关记忆。</p>
          </div>
          <div className="action-row">
            <button className="secondary-button" type="button" onClick={() => void loadMemories()} disabled={busy}>
              刷新
            </button>
            <button className="secondary-button" type="button" onClick={() => void handleRebuild()} disabled={busy || rebuilding}>
              {rebuilding ? "重建中..." : "从最近任务重建"}
            </button>
            <button className="ghost-button danger" type="button" onClick={() => setPendingDelete({ kind: "clear" })} disabled={busy || rebuilding || memories.length === 0}>
              清空
            </button>
          </div>
        </div>

        {rebuilding ? (
          <div className="banner info">正在调用 LLM 从最近任务总结长期记忆，请稍候...</div>
        ) : null}
        {errorMessage ? <div className="banner error">{errorMessage}</div> : null}
        {message ? <div className="banner success">{message}</div> : null}

        <div className="memory-list">
          {memories.map((memory) => {
            const expanded = expandedMemoryId === memory.id;
            return (
              <article key={memory.id} className={`memory-item${expanded ? " expanded" : ""}`}>
                <div className="timeline-title-row">
                  <button
                    className="skill-arrow-button"
                    type="button"
                    aria-label={expanded ? "收起记忆" : "展开记忆"}
                    onClick={() => setExpandedMemoryId(expanded ? null : memory.id)}
                  >
                    {expanded ? "▾" : "▸"}
                  </button>
                  <div>
                    <div className="skill-title-line">
                      <strong>{memory.task_name}</strong>
                      <span>{memory.outcome === "completed" ? "成功" : "失败"}</span>
                      <span>{memory.source === "llm" ? "LLM 生成" : "非 LLM 生成"}</span>
                    </div>
                    <p className="muted-copy">
                      {repoLabel(memory.repo_source)} · {formatDisplayTime(memory.updated_at)}
                    </p>
                  </div>
                  <div className="action-row">
                    <button
                      className="ghost-button danger"
                      type="button"
                      onClick={() => setPendingDelete({ kind: "memory", memory })}
                      disabled={busy || rebuilding}
                    >
                      删除
                    </button>
                  </div>
                </div>

                {expanded ? (
                  <div className="memory-detail">
                    {memory.source !== "llm" ? (
                      <div className="memory-source-note">
                        该记忆由规则回退生成，未经过 LLM 总结，信息可能偏流水账。
                      </div>
                    ) : null}
                    <div className="memory-tags">
                      {memory.tags.map((tag) => (
                        <span key={tag}>{tag}</span>
                      ))}
                    </div>
                    <div className="conversation-markdown memory-markdown">
                      {renderMarkdown(memory.content)}
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })}

          {!memories.length ? (
            <div className="empty-state inline">
              <strong>暂无长期记忆</strong>
              <p>运行任务后系统会自动沉淀，也可以点击“从最近任务重建”。</p>
            </div>
          ) : null}
        </div>
      </section>

      {pendingDelete ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setPendingDelete(null)}>
          <section className="settings-modal delete-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="delete-memory-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="settings-modal-header">
              <div>
                <h2 id="delete-memory-title">{pendingDelete.kind === "clear" ? "清空长期记忆" : "删除长期记忆"}</h2>
                <p>{pendingDelete.kind === "clear" ? "确认后将清空全部长期记忆，此操作不会删除任务记录。" : "确认后将删除该长期记忆，此操作不可恢复。"}</p>
              </div>
              <button className="modal-close-button" type="button" onClick={() => setPendingDelete(null)}>关闭</button>
            </div>
            <div className="delete-confirm-body">
              <div className="delete-confirm-card">
                <span>{pendingDelete.kind === "clear" ? "清空范围" : "记忆名称"}</span>
                <strong>{pendingDelete.kind === "clear" ? "全部长期记忆" : pendingDelete.memory.task_name}</strong>
              </div>
              <div className="delete-confirm-actions">
                <button
                  className="primary-button delete-confirm-button"
                  type="button"
                  onClick={() => pendingDelete.kind === "clear" ? void handleClear() : void handleDelete(pendingDelete.memory)}
                  disabled={busy || rebuilding}
                >
                  {busy ? (pendingDelete.kind === "clear" ? "清空中..." : "删除中...") : (pendingDelete.kind === "clear" ? "确认清空" : "确认删除")}
                </button>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
