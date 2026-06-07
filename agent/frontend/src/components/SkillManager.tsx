import { FormEvent, useEffect, useState } from "react";
import { createSkill, deleteSkill, updateSkillEnabled } from "../services/api";
import type { SkillCreateRequest, SkillRecord } from "../types/task";


interface SkillManagerProps {
  skills: SkillRecord[];
  onChanged: () => Promise<void>;
}

type SkillFormState = {
  name: string;
  description: string;
  allowedTools: string;
  priorityTools: string;
  body: string;
  enabled: boolean;
};

const emptyForm: SkillFormState = {
  name: "",
  description: "",
  allowedTools: "",
  priorityTools: "",
  body: "# 新 Skill\n\n描述这个 Skill 的工作流程、约束和终止条件。",
  enabled: true
};

function parseToolList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function toPayload(formState: SkillFormState): SkillCreateRequest {
  return {
    name: formState.name.trim(),
    description: formState.description.trim(),
    allowed_tools: parseToolList(formState.allowedTools),
    priority_tools: parseToolList(formState.priorityTools),
    body: formState.body.trim(),
    enabled: formState.enabled
  };
}

export function SkillManager({ skills, onChanged }: SkillManagerProps) {
  const [expanded, setExpanded] = useState<string | null>(skills[0]?.name ?? null);
  const [busySkill, setBusySkill] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formState, setFormState] = useState<SkillFormState>(emptyForm);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);





  async function handleToggle(skill: SkillRecord) {
    try {
      setBusySkill(skill.name);
      setErrorMessage(null);
      setSuccessMessage(null);
      await updateSkillEnabled(skill.name, !skill.enabled);
      await onChanged();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "更新 Skill 状态失败");
    } finally {
      setBusySkill(null);
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = toPayload(formState);
    if (!payload.name || !payload.description || !payload.body) {
      setErrorMessage("请填写名称、描述和正文。");
      return;
    }

    try {
      setSubmitting(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      const skill = await createSkill(payload);
      setFormState(emptyForm);
      setExpanded(skill.name);
      setShowCreateForm(false);        // 新增成功后自动折叠表单
      setSuccessMessage(`已添加 Skill：${skill.name}`);
      await onChanged();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "新增 Skill 失败");
    } finally {
      setSubmitting(false);
    }
  }


  async function handleDelete(skill: SkillRecord) {
    if (skill.builtin) {
      return;
    }
    const confirmed = window.confirm(`确定删除 Skill "${skill.name}" 吗？这会删除对应的 SKILL.md 文件。`);
    if (!confirmed) {
      return;
    }

    try {
      setBusySkill(skill.name);
      setErrorMessage(null);
      setSuccessMessage(null);
      await deleteSkill(skill.name);
      setExpanded((current) => (current === skill.name ? null : current));
      setSuccessMessage(`已删除 Skill：${skill.name}`);
      await onChanged();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "删除 Skill 失败");
    } finally {
      setBusySkill(null);
    }
  }

  return (
    <section id="skills" className="card skill-manager-panel">
      <div className="section-header">
        <div>
          <h2>Skill 管理</h2>
          <p>查看现有 Skill，添加自定义 Skill，并控制新任务默认启用范围。</p>
        </div>
      </div>

      {errorMessage ? <div className="banner error">{errorMessage}</div> : null}
      {successMessage ? <div className="banner success">{successMessage}</div> : null}

      <article className="skill-manager-item skill-create-item">
        {/* 折叠式新增 Skill 标题行 */}
        <div
          className="section-header compact"
          style={{ cursor: 'pointer' }}
          onClick={() => setShowCreateForm(!showCreateForm)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setShowCreateForm(!showCreateForm);
            }
          }}
        >
          <div>
            <h3>自定义 Skill</h3>
            <p>创建新的 Skill</p>
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={(e) => {
              e.stopPropagation();
              setShowCreateForm(!showCreateForm);
            }}
          >
            {showCreateForm ? '取消' : '创建'}
          </button>
        </div>

        {/* 新增表单（可折叠） */}
        {showCreateForm && (
          <form className="skill-create-form" onSubmit={(event) => void handleCreate(event)}>
            <div className="skill-form-grid">
              <label>
                <span>名称</span>
                <input
                  value={formState.name}
                  onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
                  placeholder="my-custom-skill"
                />
              </label>
              <label>
                <span>描述</span>
                <input
                  value={formState.description}
                  onChange={(event) => setFormState((current) => ({ ...current, description: event.target.value }))}
                  placeholder="一句话说明什么时候使用"
                />
              </label>
              <label>
                <span>优先工具</span>
                <input
                  value={formState.priorityTools}
                  onChange={(event) => setFormState((current) => ({ ...current, priorityTools: event.target.value }))}
                  placeholder="read_file, search_code"
                />
              </label>
              <label>
                <span>允许工具</span>
                <input
                  value={formState.allowedTools}
                  onChange={(event) => setFormState((current) => ({ ...current, allowedTools: event.target.value }))}
                  placeholder="read_file, search_code, patch_file"
                />
              </label>
            </div>

            <label className="skill-body-field">
              <span>正文</span>
              <textarea
                value={formState.body}
                onChange={(event) => setFormState((current) => ({ ...current, body: event.target.value }))}
                rows={10}
              />
            </label>

            <div className="action-row">
              <button className="primary-button" type="submit" disabled={submitting}>
                {submitting ? '保存中' : '添加 Skill'}
              </button>
            </div>
          </form>
        )}
      </article>

      <div className="skill-manager-list">
        {skills.map((skill) => {
          const isExpanded = expanded === skill.name;
          return (
            <article key={skill.name} className="skill-manager-item">
              <div className="timeline-title-row">
                <div>
                  <div className="skill-title-line">
                    <strong>{skill.name}</strong>
                    {skill.builtin ? <span>内置</span> : <span>自定义</span>}
                  </div>
                  <p className="muted-copy">{skill.description}</p>
                </div>
                <div className="action-row">
                  <button className="secondary-button" type="button" onClick={() => setExpanded(isExpanded ? null : skill.name)}>
                    {isExpanded ? "收起" : "查看"}
                  </button>
                  <button
                    className={skill.enabled ? "primary-button" : "secondary-button"}
                    type="button"
                    onClick={() => void handleToggle(skill)}
                    disabled={busySkill === skill.name}
                  >
                    {skill.enabled ? "已启用" : "已禁用"}
                  </button>
                  {!skill.builtin ? (
                    <button
                      className="ghost-button danger"
                      type="button"
                      onClick={() => void handleDelete(skill)}
                      disabled={busySkill === skill.name}
                    >
                      删除
                    </button>
                  ) : null}
                </div>
              </div>

              {isExpanded ? (
                <div className="skill-detail-grid">
                  <div>
                    <span>优先工具</span>
                    <p>{skill.priority_tools.join(", ") || "无"}</p>
                  </div>
                  <div>
                    <span>允许工具</span>
                    <p>{skill.allowed_tools.join(", ") || "无"}</p>
                  </div>
                  <pre>{skill.body}</pre>
                </div>
              ) : null}
            </article>
          );
        })}
        {!skills.length ? (
          <div className="empty-state inline">
            <strong>未检测到 Skill</strong>
            <p>后端没有从 gitIssueAssitant/skills 读取到 SKILL.md。</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
