import { useState } from "react";
import { deleteBadCase, rerunBadCase, updateBadCase } from "../services/api";
import type { BadCaseRecord } from "../types/task";

interface BadCasePanelProps {
  badCases: BadCaseRecord[];
  defaultTags: string[];
  onChanged: () => Promise<void>;
  onTaskCreated: () => Promise<void>;
}

export function BadCasePanel({ badCases, defaultTags, onChanged, onTaskCreated }: BadCasePanelProps) {
  const [selectedId, setSelectedId] = useState<string | null>(badCases[0]?.id ?? null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const selected = badCases.find((item) => item.id === selectedId) ?? badCases[0] ?? null;

  async function toggleTag(record: BadCaseRecord, tag: string) {
    const nextTags = record.tags.includes(tag)
      ? record.tags.filter((item) => item !== tag)
      : [...record.tags, tag];
    try {
      setBusyId(record.id);
      setErrorMessage(null);
      await updateBadCase(record.id, { tags: nextTags, note: record.note });
      await onChanged();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "更新 Bad Case 失败");
    } finally {
      setBusyId(null);
    }
  }

  async function updateNote(record: BadCaseRecord, note: string) {
    try {
      setBusyId(record.id);
      setErrorMessage(null);
      await updateBadCase(record.id, { tags: record.tags, note });
      await onChanged();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "更新备注失败");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(record: BadCaseRecord) {
    if (!window.confirm("确认删除该 Bad Case 吗？")) {
      return;
    }
    try {
      setBusyId(record.id);
      await deleteBadCase(record.id);
      setSelectedId(null);
      await onChanged();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "删除 Bad Case 失败");
    } finally {
      setBusyId(null);
    }
  }

  async function handleRerun(record: BadCaseRecord) {
    try {
      setBusyId(record.id);
      setErrorMessage(null);
      await rerunBadCase(record.id, { auto_start: false });
      await onTaskCreated();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "重新创建任务失败");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section id="bad-cases" className="card bad-case-panel">
      <div className="section-header">
        <div>
          <h2>Bad Case 数据集</h2>
          <p>沉淀失败样例、归因标签和复跑入口。</p>
        </div>
      </div>

      {errorMessage ? <div className="banner error">{errorMessage}</div> : null}

      <div className="bad-case-layout">
        <div className="bad-case-list">
          {badCases.map((record) => (
            <button
              key={record.id}
              className={`bad-case-item ${selected?.id === record.id ? "active" : ""}`}
              type="button"
              onClick={() => setSelectedId(record.id)}
            >
              <strong>{record.task_name}</strong>
              <span>{record.status}</span>
              <small>{record.tags.join(" / ") || "未标注"}</small>
            </button>
          ))}
          {!badCases.length ? (
            <div className="empty-state inline">
              <strong>暂无 Bad Case</strong>
              <p>在任务详情中点击“保存 Bad Case”后会出现在这里。</p>
            </div>
          ) : null}
        </div>

        {selected ? (
          <article className="bad-case-detail">
            <div className="section-header compact">
              <div>
                <h3>{selected.task_name}</h3>
                <p>{selected.id} / 来源任务 {selected.source_task_id}</p>
              </div>
              <div className="action-row">
                <button className="secondary-button" type="button" onClick={() => void handleRerun(selected)} disabled={busyId === selected.id}>
                  重新创建任务
                </button>
                <button className="ghost-button danger" type="button" onClick={() => void handleDelete(selected)} disabled={busyId === selected.id}>
                  删除
                </button>
              </div>
            </div>

            <p className="paragraph-block">{selected.summary || selected.issue_input}</p>

            <div className="tag-grid">
              {defaultTags.map((tag) => (
                <label key={tag} className="checkbox-row tag-choice">
                  <input
                    type="checkbox"
                    checked={selected.tags.includes(tag)}
                    onChange={() => void toggleTag(selected, tag)}
                    disabled={busyId === selected.id}
                  />
                  <span>{tag}</span>
                </label>
              ))}
            </div>

            <label className="bad-case-note">
              <span>备注</span>
              <textarea
                rows={3}
                defaultValue={selected.note}
                onBlur={(event) => void updateNote(selected, event.target.value)}
                placeholder="记录失败原因、复测建议或环境限制"
              />
            </label>

            <div className="two-column-panel">
              <div>
                <h4>Diff 摘要</h4>
                <pre className="git-output-viewer">{selected.diff_summary || "无 diff 摘要"}</pre>
              </div>
              <div>
                <h4>测试输出摘要</h4>
                <pre className="git-output-viewer">{selected.test_output_summary || "无测试输出"}</pre>
              </div>
            </div>
          </article>
        ) : null}
      </div>
    </section>
  );
}
