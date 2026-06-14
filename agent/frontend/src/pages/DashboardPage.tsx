import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import type {
  AppSettings,
  CreateTaskPayload,
  GitHubIssueSummary,
  SkillRecord
} from "../types/task";
import { fetchRepoIssues } from "../services/api";

interface DashboardPageProps {
  busyTaskId: string | null;
  settings: AppSettings | null;
  models: string[];
  skills: SkillRecord[];
  onCreateTask: (payload: CreateTaskPayload) => Promise<void>;
}

interface SkillTriggerState {
  query: string;
  start: number;
  end: number;
}

interface SkillMentionRange {
  start: number;
  end: number;
  text: string;
}

function looksLikeGitHubUrl(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  return /github\.com[/:][\w.-]+\/[\w.-]+/.test(trimmed);
}

function findSkillTrigger(value: string, caretPosition: number): SkillTriggerState | null {
  const prefix = value.slice(0, caretPosition);
  const match = prefix.match(/(^|\s)\$([A-Za-z0-9_-]*)$/);
  if (!match) {
    return null;
  }
  return {
    query: match[2],
    start: prefix.length - match[2].length - 1,
    end: caretPosition
  };
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function isSkillMentionBoundary(value: string | undefined): boolean {
  return !value || /[\s.,;:!?()[\]{}"'`，。！？；：（）【】]/.test(value);
}

function findSkillMentionRanges(value: string, skillNames: string[]): SkillMentionRange[] {
  if (!value || !skillNames.length) {
    return [];
  }

  const pattern = skillNames
    .filter(Boolean)
    .sort((left, right) => right.length - left.length)
    .map(escapeRegExp)
    .join("|");

  if (!pattern) {
    return [];
  }

  const regex = new RegExp(pattern, "g");
  const ranges: SkillMentionRange[] = [];

  for (const match of value.matchAll(regex)) {
    const start = match.index ?? 0;
    const text = match[0];
    const end = start + text.length;

    if (!isSkillMentionBoundary(value[start - 1]) || !isSkillMentionBoundary(value[end])) {
      continue;
    }

    ranges.push({ start, end, text });
  }

  return ranges;
}

function renderSkillHighlightedText(value: string, skillNames: string[]): ReactNode {
  if (!value || !skillNames.length) {
    return value;
  }

  const nodes: ReactNode[] = [];
  const ranges = findSkillMentionRanges(value, skillNames);
  let lastIndex = 0;

  for (const range of ranges) {
    if (range.start > lastIndex) {
      nodes.push(value.slice(lastIndex, range.start));
    }
    nodes.push(
      <span className="skill-inline-token" key={`${range.text}-${range.start}`}>
        {range.text}
      </span>
    );
    lastIndex = range.end;
  }

  if (lastIndex < value.length) {
    nodes.push(value.slice(lastIndex));
  }

  return nodes.length ? nodes : value;
}

export function DashboardPage({
  busyTaskId,
  settings,
  models,
  skills,
  onCreateTask
}: DashboardPageProps) {
  const descriptionTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const descriptionHighlightRef = useRef<HTMLDivElement | null>(null);
  const [skillTrigger, setSkillTrigger] = useState<SkillTriggerState | null>(null);
  const [formState, setFormState] = useState<CreateTaskPayload>({
    name: "",
    description: "",
    auto_start: true,
    config: {
      repo_source: "",
      issue_input: "",
      target_dir: "",
      model_name: settings?.model_name || models[0] || "",
      run_mode: "auto",
      enabled_skills: null
    }
  });
  const [issuesList, setIssuesList] = useState<GitHubIssueSummary[]>([]);
  const [loadingIssues, setLoadingIssues] = useState(false);
  const [issuesError, setIssuesError] = useState<string | null>(null);
  const [selectedIssueNumber, setSelectedIssueNumber] = useState<number | null>(null);
  const [selectedIssueBody, setSelectedIssueBody] = useState<string>("");
  const [issuesModalOpen, setIssuesModalOpen] = useState(false);
  const [skillPickerOpen, setSkillPickerOpen] = useState(false);
  const issuesFetchAbortRef = useRef<AbortController | null>(null);
  const descriptionSkillNames = useMemo(() => skills.map((skill) => skill.name), [skills]);
  const skillSuggestions = useMemo(() => {
    if (!skillTrigger) {
      return [];
    }
    const query = skillTrigger.query.toLowerCase();
    return skills.filter((skill) => {
      if (!query) {
        return true;
      }
      return (
        skill.name.toLowerCase().includes(query) ||
        skill.description.toLowerCase().includes(query)
      );
    });
  }, [skillTrigger, skills]);

  useEffect(() => {
    const enabledSkillNames = skills.filter((skill) => skill.enabled).map((skill) => skill.name);
    setFormState((current) => {
      if (current.config.enabled_skills !== null && current.config.enabled_skills !== undefined) {
        return current;
      }
      return {
        ...current,
        config: { ...current.config, enabled_skills: enabledSkillNames }
      };
    });
  }, [skills]);

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

  const handleRepoSourceChange = useCallback((value: string) => {
    setFormState((current) => ({
      ...current,
      config: { ...current.config, repo_source: value }
    }));
    // Clear issues when the repo URL changes
    if (issuesFetchAbortRef.current) {
      issuesFetchAbortRef.current.abort();
      issuesFetchAbortRef.current = null;
    }
    setIssuesList([]);
    setIssuesError(null);
    setSelectedIssueNumber(null);
    setSelectedIssueBody("");
    setIssuesModalOpen(false);
  }, []);

  async function handleFetchIssues() {
    const repoSource = formState.config.repo_source.trim();
    if (!repoSource) return;

    if (issuesFetchAbortRef.current) {
      issuesFetchAbortRef.current.abort();
    }
    const controller = new AbortController();
    issuesFetchAbortRef.current = controller;

    setLoadingIssues(true);
    setIssuesError(null);
    setIssuesList([]);
    setIssuesModalOpen(true);

    try {
      const issues = await fetchRepoIssues(repoSource);
      if (controller.signal.aborted) return;
      setIssuesList(issues);
      if (issues.length === 0) {
        setIssuesError("该仓库没有找到 open 状态的 Issue");
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      setIssuesError(error instanceof Error ? error.message : "获取 Issues 失败");
    } finally {
      if (!controller.signal.aborted) {
        setLoadingIssues(false);
        issuesFetchAbortRef.current = null;
      }
    }
  }

  function handleRepoSourceKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      if (looksLikeGitHubUrl(formState.config.repo_source)) {
        void handleFetchIssues();
      }
    }
  }

  function handleSelectIssue(issue: GitHubIssueSummary) {
    setSelectedIssueNumber(issue.number);
    setSelectedIssueBody(issue.body);
    setFormState((current) => ({
      ...current,
      config: { ...current.config, issue_input: `#${issue.number}` }
    }));
    setIssuesModalOpen(false);
  }

  function handleDescriptionChange(value: string, caretPosition: number | null) {
    setFormState((current) => ({ ...current, description: value }));
    setSkillTrigger(caretPosition === null ? null : findSkillTrigger(value, caretPosition));
  }

  function handleDescriptionKeyUp() {
    const textarea = descriptionTextareaRef.current;
    if (!textarea) {
      setSkillTrigger(null);
      return;
    }
    setSkillTrigger(findSkillTrigger(textarea.value, textarea.selectionStart));
  }

  function handleDescriptionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Escape" && skillTrigger) {
      event.preventDefault();
      setSkillTrigger(null);
      return;
    }

    if (event.key !== "Backspace") {
      return;
    }

    const textarea = descriptionTextareaRef.current;
    if (!textarea) {
      return;
    }

    const selectionStart = textarea.selectionStart;
    const selectionEnd = textarea.selectionEnd;
    if (selectionStart != selectionEnd) {
      return;
    }

    const mentions = findSkillMentionRanges(formState.description, descriptionSkillNames);
    const matchedMention = mentions.find((mention) => {
      if (mention.end === selectionStart) {
        return true;
      }
      return mention.end + 1 === selectionStart && /\s/.test(formState.description[mention.end] ?? "");
    });

    if (!matchedMention) {
      return;
    }

    event.preventDefault();
    const deleteUntil = matchedMention.end + (
      matchedMention.end + 1 === selectionStart && /\s/.test(formState.description[matchedMention.end] ?? "")
        ? 1
        : 0
    );
    const nextDescription = (
      `${formState.description.slice(0, matchedMention.start)}${formState.description.slice(deleteUntil)}`
    );
    setFormState((current) => ({ ...current, description: nextDescription }));
    setSkillTrigger(findSkillTrigger(nextDescription, matchedMention.start));
    window.requestAnimationFrame(() => {
      const activeTextarea = descriptionTextareaRef.current;
      if (!activeTextarea) {
        return;
      }
      activeTextarea.focus();
      activeTextarea.setSelectionRange(matchedMention.start, matchedMention.start);
    });
  }

  function handleDescriptionScroll() {
    const textarea = descriptionTextareaRef.current;
    const highlight = descriptionHighlightRef.current;
    if (!textarea || !highlight) {
      return;
    }
    highlight.scrollTop = textarea.scrollTop;
    highlight.scrollLeft = textarea.scrollLeft;
  }

  function handleSelectSkill(skill: SkillRecord) {
    if (!skillTrigger) {
      return;
    }
    const nextDescription = (
      `${formState.description.slice(0, skillTrigger.start)}${skill.name} ${formState.description.slice(skillTrigger.end)}`
    );
    const nextCaretPosition = skillTrigger.start + skill.name.length + 1;
    setFormState((current) => ({ ...current, description: nextDescription }));
    setSkillTrigger(null);
    window.requestAnimationFrame(() => {
      const textarea = descriptionTextareaRef.current;
      if (!textarea) {
        return;
      }
      textarea.focus();
      textarea.setSelectionRange(nextCaretPosition, nextCaretPosition);
    });
  }

  function handleToggleExposedSkill(skillName: string, checked: boolean) {
    setFormState((current) => {
      const currentSkills = current.config.enabled_skills ?? [];
      const nextSkills = checked
        ? Array.from(new Set([...currentSkills, skillName]))
        : currentSkills.filter((name) => name !== skillName);
      return {
        ...current,
        config: { ...current.config, enabled_skills: nextSkills }
      };
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await onCreateTask({
        ...formState,
        config: {
          ...formState.config,
          target_dir: formState.config.target_dir?.trim() || null,
          model_name: formState.config.model_name?.trim() || null,
          enabled_skills: formState.config.enabled_skills ?? null
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
          run_mode: "auto",
          enabled_skills: skills.length
            ? skills.filter((skill) => skill.enabled).map((skill) => skill.name)
            : null
        }
      });
      setIssuesList([]);
      setIssuesError(null);
      setSelectedIssueNumber(null);
      setSelectedIssueBody("");
      setIssuesModalOpen(false);
      setSkillPickerOpen(false);
    } catch {
      // App already surfaces the error banner.
    }
  }

  return (
    <section className="card composer-card">
      <div className="section-header">
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
          <div className="repo-source-row">
            <input
              required
              className="repo-source-input"
              value={formState.config.repo_source}
              onChange={(event) => handleRepoSourceChange(event.target.value)}
              onKeyDown={handleRepoSourceKeyDown}
              placeholder="例如：repos/myproject 或 https://github.com/org/repo.git"
            />
            {looksLikeGitHubUrl(formState.config.repo_source) ? (
              <button
                type="button"
                className="secondary-button fetch-issues-btn"
                disabled={loadingIssues}
                onClick={() => void handleFetchIssues()}
              >
                {loadingIssues ? "获取中..." : "浏览 Issues"}
              </button>
            ) : null}
          </div>
        </label>

        <label>
          <span>Issue 描述 / 编号 / 链接</span>
          <textarea
            required
            rows={2}
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
          <div className="skill-suggest-wrapper">
            <div className="skill-highlight-input">
              <div className="skill-highlight-layer" ref={descriptionHighlightRef} aria-hidden="true">
                {renderSkillHighlightedText(formState.description, descriptionSkillNames)}
              </div>
              <textarea
                ref={descriptionTextareaRef}
                className="skill-highlight-textarea"
                rows={2}
                value={formState.description}
                onChange={(event) =>
                  handleDescriptionChange(event.target.value, event.target.selectionStart)
                }
                onKeyUp={handleDescriptionKeyUp}
                onKeyDown={handleDescriptionKeyDown}
                onScroll={handleDescriptionScroll}
                onClick={handleDescriptionKeyUp}
                placeholder="记录预期修复范围、限制条件或上下文说明。输入 $ 选择 Skill，例如：使用 $i-am-a-cat skill"
              />
            </div>
            {skillTrigger ? (
              <div className="skill-suggest-menu" role="listbox" aria-label="选择 Skill">
                {skillSuggestions.map((skill) => (
                  <button
                    key={skill.name}
                    type="button"
                    role="option"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleSelectSkill(skill)}
                  >
                    <strong>{skill.name}</strong>
                    <span>{skill.description}</span>
                  </button>
                ))}
                {!skillSuggestions.length ? (
                  <div className="skill-suggest-empty">没有匹配的 Skill</div>
                ) : null}
              </div>
            ) : null}
          </div>
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

        </div>

        <div className="skill-exposure-picker">
          <span className="field-label">暴露给 Agent 的 Skill</span>
          <button
            className="skill-picker-entry"
            type="button"
            onClick={() => setSkillPickerOpen(true)}
          >
            <span>选择 Skill</span>
            <strong>
              {formState.config.enabled_skills?.length ?? 0}/{skills.length || 0} 已选择
            </strong>
          </button>
          <p className="muted-copy">只有选中的 Skill 会暴露给 Agent 选择使用。</p>
        </div>

        <div className="action-row">
          <button className="primary-button" type="submit" disabled={busyTaskId === "create"}>
            创建任务
          </button>
        </div>
      </form>

      {issuesModalOpen ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setIssuesModalOpen(false)}>
          <section className="settings-modal issues-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
            <div className="settings-modal-header">
              <div>
                <h2>选择 Issue</h2>
                <p>从仓库中选择一个 Issue 来创建任务</p>
              </div>
              <button className="modal-close-button" type="button" onClick={() => setIssuesModalOpen(false)}>关闭</button>
            </div>
            <div className="issues-modal-body">
              {loadingIssues ? (
                <div className="issues-modal-loading">
                  <p className="muted-copy">正在加载 Issues...</p>
                </div>
              ) : issuesError ? (
                <div className="issues-modal-error">
                  <p className="error-copy">{issuesError}</p>
                </div>
              ) : issuesList.length > 0 ? (
                <>
                  <div className="issues-modal-header-info">
                    <span>共 {issuesList.length} 个 Issue</span>
                  </div>
                  <ul className="issues-modal-list">
                    {issuesList.map((issue) => (
                      <li key={issue.number}>
                        <button
                          type="button"
                          className={`issue-modal-item ${issue.number === selectedIssueNumber ? "selected" : ""}`}
                          onClick={() => handleSelectIssue(issue)}
                        >
                          <div className="issue-modal-item-header">
                            <span className="issue-number">#{issue.number}</span>
                            <span className="issue-title">{issue.title}</span>
                          </div>
                          <div className="issue-modal-item-meta">
                            <span className={`issue-state issue-state-${issue.state}`}>
                              {issue.state === "open" ? "Open" : issue.state}
                            </span>
                            {issue.labels.length > 0 ? (
                              <div className="issue-labels">
                                {issue.labels.map((label) => (
                                  <span key={label} className="issue-label-tag">{label}</span>
                                ))}
                              </div>
                            ) : null}
                          </div>
                          {issue.body ? (
                            <p className="issue-body-preview">{issue.body.slice(0, 150)}{issue.body.length > 150 ? "..." : ""}</p>
                          ) : null}
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <div className="issues-modal-empty">
                  <p className="muted-copy">暂无 Issues</p>
                </div>
              )}
            </div>
          </section>
        </div>
      ) : null}

      {skillPickerOpen ? (
        <div className="modal-backdrop skill-modal-backdrop" role="presentation" onMouseDown={() => setSkillPickerOpen(false)}>
          <section
            className="settings-modal skill-exposure-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="skill-exposure-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="settings-modal-header">
              <div>
                <h2 id="skill-exposure-title">选择暴露给 Agent 的 Skill</h2>
                <p>Agent 只会从这里选中的 Skill 中进行路由选择。</p>
              </div>
              <button className="modal-close-button" type="button" onClick={() => setSkillPickerOpen(false)}>关闭</button>
            </div>

            <div className="skill-exposure-body">
              <div className="skill-exposure-summary">
                <span>已选择 {formState.config.enabled_skills?.length ?? 0} 个</span>
                <div>
                  <button
                    type="button"
                    onClick={() =>
                      setFormState((current) => ({
                        ...current,
                        config: { ...current.config, enabled_skills: skills.map((skill) => skill.name) }
                      }))
                    }
                    disabled={!skills.length}
                  >
                    全选
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setFormState((current) => ({
                        ...current,
                        config: { ...current.config, enabled_skills: [] }
                      }))
                    }
                    disabled={!skills.length}
                  >
                    清空
                  </button>
                </div>
              </div>

              <div className="skill-exposure-list">
                {skills.map((skill) => {
                  const checked = formState.config.enabled_skills?.includes(skill.name) ?? false;
                  return (
                    <label key={skill.name} className="checkbox-row skill-exposure-choice">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) => handleToggleExposedSkill(skill.name, event.target.checked)}
                      />
                      <span>
                        <strong>{skill.name}</strong>
                        <small>{skill.description}</small>
                      </span>
                    </label>
                  );
                })}
                {!skills.length ? <p className="muted-copy">未检测到可用 Skill。</p> : null}
              </div>

              <div className="skill-modal-actions">
                <button className="primary-button" type="button" onClick={() => setSkillPickerOpen(false)}>
                  完成
                </button>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
