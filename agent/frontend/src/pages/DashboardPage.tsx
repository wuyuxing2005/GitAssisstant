import { useEffect, useState, type FormEvent } from "react";
import type {
  AppSettings,
  CreateTaskPayload,
  RunMode,
  SkillRecord
} from "../types/task";

interface DashboardPageProps {
  busyTaskId: string | null;
  settings: AppSettings | null;
  models: string[];
  skills: SkillRecord[];
  onCreateTask: (payload: CreateTaskPayload) => Promise<void>;
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
      max_iterations: 15,
      run_mode: "auto",
      enabled_skills: []
    }
  });

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
          max_iterations: 15,
          run_mode: "auto",
          enabled_skills: skills.filter((skill) => skill.enabled).map((skill) => skill.name)
        }
      });
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
          <input
            required
            value={formState.config.repo_source}
            onChange={(event) =>
              setFormState((current) => ({
                ...current,
                config: { ...current.config, repo_source: event.target.value }
              }))
            }
            placeholder="例如：repos/myproject 或 https://github.com/org/repo.git"
          />
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

          <label>
            <span>最大轮数</span>
            <input
              type="number"
              min={1}
              max={50}
              value={formState.config.max_iterations}
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  config: {
                    ...current.config,
                    max_iterations: Number(event.target.value) || 15
                  }
                }))
              }
            />
          </label>

          <label>
            <span>运行模式</span>
            <select
              value={formState.config.run_mode}
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  config: {
                    ...current.config,
                    run_mode: event.target.value as RunMode
                  }
                }))
              }
            >
              <option value="auto">auto</option>
              <option value="step">step</option>
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
                <label key={skill.name} className="checkbox-row skill-choice">
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
                  <small>{skill.description}</small>
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
    </section>
  );
}
