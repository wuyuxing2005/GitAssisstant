import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
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

function looksLikeGitHubUrl(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  return /github\.com[/:][\w.-]+\/[\w.-]+/.test(trimmed);
}

export function DashboardPage({
  busyTaskId,
  settings,
  models,
  skills,
  onCreateTask
}: DashboardPageProps) {
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
      enabled_skills: []
    }
  });
  const [issuesList, setIssuesList] = useState<GitHubIssueSummary[]>([]);
  const [loadingIssues, setLoadingIssues] = useState(false);
  const [issuesError, setIssuesError] = useState<string | null>(null);
  const [selectedIssueNumber, setSelectedIssueNumber] = useState<number | null>(null);
  const [selectedIssueBody, setSelectedIssueBody] = useState<string>("");
  const [issuesModalOpen, setIssuesModalOpen] = useState(false);
  const issuesFetchAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const enabledSkillNames = skills.filter((skill) => skill.enabled).map((skill) => skill.name);
    setFormState((current) => {
      if (current.config.enabled_skills && current.config.enabled_skills.length > 0) {
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await onCreateTask({
        ...formState,
        config: {
          ...formState.config,
          target_dir: formState.config.target_dir?.trim() || null,
          model_name: formState.config.model_name?.trim() || null,
          enabled_skills: formState.config.enabled_skills ?? []
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
          enabled_skills: skills.filter((skill) => skill.enabled).map((skill) => skill.name)
        }
      });
      setIssuesList([]);
      setIssuesError(null);
      setSelectedIssueNumber(null);
      setSelectedIssueBody("");
      setIssuesModalOpen(false);
    } catch {
      // App already surfaces the error banner.
    }
  }

  return (
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

        <div className="skill-picker">
          <span className="field-label">启用 Skill</span>
          <div className="skill-picker-grid">
            {skills.map((skill) => {
              const checked = formState.config.enabled_skills?.includes(skill.name) ?? false;
              return (
                <label key={skill.name} className="checkbox-row skill-choice" data-summary={skill.description}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) =>
                      setFormState((current) => {
                        const currentSkills = current.config.enabled_skills ?? [];
                        const nextSkills = event.target.checked
                          ? Array.from(new Set([...currentSkills, skill.name]))
                          : currentSkills.filter((name) => name !== skill.name);
                        return {
                          ...current,
                          config: { ...current.config, enabled_skills: nextSkills }
                        };
                      })
                    }
                  />
                  <span>{skill.name}</span>
                </label>
              );
            })}
            {!skills.length ? <p className="muted-copy">未检测到可用 Skill。</p> : null}
          </div>
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
    </section>
  );
}
