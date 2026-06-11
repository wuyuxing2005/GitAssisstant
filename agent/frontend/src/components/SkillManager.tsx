import { FormEvent, useState } from "react";
import { createSkill, deleteSkill } from "../services/api";
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
  const [createErrorMessage, setCreateErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<SkillRecord | null>(null);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = toPayload(formState);
    if (!payload.name || !payload.description || !payload.body) {
      setCreateErrorMessage("请填写名称、描述和正文。");
      return;
    }
    const confirmed = window.confirm(editingSkill ? `确定保存对 Skill "${editingSkill.name}" 的修改吗？` : `确定创建 Skill "${payload.name}" 吗？`);
    if (!confirmed) {
      return;
    }

    try {
      setSubmitting(true);
      setCreateErrorMessage(null);
      setSuccessMessage(null);
      let skill: SkillRecord;
      if (editingSkill) {
        if (payload.name === editingSkill.name) {
          await deleteSkill(editingSkill.name);
          skill = await createSkill(payload);
        } else {
          skill = await createSkill(payload);
          await deleteSkill(editingSkill.name);
        }
      } else {
        skill = await createSkill(payload);
      }
      setFormState(emptyForm);
      setExpanded(skill.name);
      setCreateModalOpen(false);
      setEditingSkill(null);
      setSuccessMessage(editingSkill ? `已更新 Skill：${skill.name}` : `已添加 Skill：${skill.name}`);
      await onChanged();
    } catch (error) {
      setCreateErrorMessage(error instanceof Error ? error.message : editingSkill ? "编辑 Skill 失败" : "新增 Skill 失败");
    } finally {
      setSubmitting(false);
    }
  }

  function handleOpenCreateModal() {
    setFormState(emptyForm);
    setEditingSkill(null);
    setCreateErrorMessage(null);
    setCreateModalOpen(true);
  }

  function handleCloseCreateModal() {
    setCreateModalOpen(false);
    setEditingSkill(null);
    setCreateErrorMessage(null);
  }

  function handleOpenEditModal(skill: SkillRecord) {
    setEditingSkill(skill);
    setFormState({
      name: skill.name,
      description: skill.description,
      allowedTools: skill.allowed_tools.join(", "),
      priorityTools: skill.priority_tools.join(", "),
      body: skill.body,
      enabled: skill.enabled
    });
    setCreateErrorMessage(null);
    setCreateModalOpen(true);
  }

  async function handleDelete(skill: SkillRecord, errorTarget: "page" | "modal" = "page"): Promise<boolean> {
    const confirmed = window.confirm(`确定删除 Skill "${skill.name}" 吗?此操作不可恢复。`);
    if (!confirmed) {
      return false;
    }

    try {
      setBusySkill(skill.name);
      setErrorMessage(null);
      setSuccessMessage(null);
      await deleteSkill(skill.name);
      setExpanded((current) => (current === skill.name ? null : current));
      setSuccessMessage(`已删除 Skill：${skill.name}`);
      await onChanged();
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : "删除 Skill 失败";
      if (errorTarget === "modal") {
        setCreateErrorMessage(message);
      } else {
        setErrorMessage(message);
      }
      return false;
    } finally {
      setBusySkill(null);
    }
  }

  async function handleDeleteEditingSkill() {
    if (!editingSkill) {
      return;
    }
    try {
      setCreateErrorMessage(null);
      const deleted = await handleDelete(editingSkill, "modal");
      if (deleted) {
        setCreateModalOpen(false);
        setEditingSkill(null);
      }
    } catch (error) {
      setCreateErrorMessage(error instanceof Error ? error.message : "删除 Skill 失败");
    }
  }

  return (
    <section id="skills" className="card skill-manager-panel">
      <div className="section-header">
        <div>
          <h2>Skill 管理</h2>
          <p>查看现有 Skill，添加自定义 Skill，并控制新任务默认启用范围。</p>
        </div>
        <button className="primary-button" type="button" onClick={handleOpenCreateModal}>
          自定义skill
        </button>
      </div>

      {errorMessage ? <div className="banner error">{errorMessage}</div> : null}
      {successMessage ? <div className="banner success">{successMessage}</div> : null}

      {createModalOpen ? (
        <div className="modal-backdrop skill-modal-backdrop" role="presentation">
          <section className="settings-modal skill-create-modal" role="dialog" aria-modal="true" aria-labelledby="skill-create-title">
            <div className="settings-modal-header">
              <div>
                <h2 id="skill-create-title">{editingSkill ? "编辑 Skill" : "自定义 Skill"}</h2>
                <p>{editingSkill ? "" : ""}</p>
              </div>
              <button className="modal-close-button skill-modal-close-button" type="button" onClick={handleCloseCreateModal} aria-label="关闭 Skill 弹窗">
                关闭
              </button>
            </div>
          <form className="skill-create-form" onSubmit={(event) => void handleCreate(event)}>
            {createErrorMessage ? <div className="banner error">{createErrorMessage}</div> : null}
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

            <div className="skill-modal-actions">
              {editingSkill ? (
                <button
                  className="trash-button"
                  type="button"
                  aria-label="删除skill"
                  title="删除skill"
                  onClick={() => void handleDeleteEditingSkill()}
                  disabled={submitting}
                >
                  <img src="/assets/删除.svg" alt="" aria-hidden="true" />
                </button>
              ) : null}
              <button className="primary-button" type="submit" disabled={submitting}>
                {submitting ? "保存中" : "确定"}
              </button>
            </div>
          </form>
          </section>
        </div>
      ) : null}

      <div className="skill-manager-list">
        {skills.map((skill) => {
          const isExpanded = expanded === skill.name;
          return (
            <article key={skill.name} className={`skill-manager-item${isExpanded ? " expanded" : ""}`}>
              <div className="timeline-title-row">
                <button
                  className="skill-arrow-button"
                  type="button"
                  aria-label={isExpanded ? "收起 Skill" : "展开 Skill"}
                  onClick={() => setExpanded(isExpanded ? null : skill.name)}
                >
                  {isExpanded ? "‹" : "›"}
                </button>
                <div>
                  <div className="skill-title-line">
                    <strong>{skill.name}</strong>
                    {skill.builtin ? <span>内置</span> : <span>自定义</span>}
                  </div>
                  <p className="muted-copy">{skill.description}</p>
                </div>
                <div className="action-row">
                  <button
                    className="edit-button"
                    type="button"
                    aria-label={`编辑 ${skill.name}`}
                    title="编辑skill"
                    onClick={() => handleOpenEditModal(skill)}
                    disabled={busySkill === skill.name}
                  >
                    <img src="/assets/edit.svg" alt="" aria-hidden="true" />
                  </button>
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
