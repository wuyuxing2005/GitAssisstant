import { useState } from "react";
import { updateSkillEnabled } from "../services/api";
import type { SkillRecord } from "../types/task";

interface SkillManagerProps {
  skills: SkillRecord[];
  onChanged: () => Promise<void>;
}

export function SkillManager({ skills, onChanged }: SkillManagerProps) {
  const [expanded, setExpanded] = useState<string | null>(skills[0]?.name ?? null);
  const [busySkill, setBusySkill] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleToggle(skill: SkillRecord) {
    try {
      setBusySkill(skill.name);
      setErrorMessage(null);
      await updateSkillEnabled(skill.name, !skill.enabled);
      await onChanged();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "更新 Skill 状态失败");
    } finally {
      setBusySkill(null);
    }
  }

  return (
    <section id="skills" className="card skill-manager-panel">
      <div className="section-header">
        <div>
          <h2>Skill 管理</h2>
          <p>查看现有 Skill，并控制新任务默认启用范围。</p>
        </div>
      </div>

      {errorMessage ? <div className="banner error">{errorMessage}</div> : null}

      <div className="skill-manager-list">
        {skills.map((skill) => {
          const isExpanded = expanded === skill.name;
          return (
            <article key={skill.name} className="skill-manager-item">
              <div className="timeline-title-row">
                <div>
                  <strong>{skill.name}</strong>
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
