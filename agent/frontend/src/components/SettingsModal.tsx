import { useEffect, useRef, useState, type FormEvent } from "react";
import type { AppSettings, AppSettingsUpdate } from "../types/task";

interface SettingsModalProps {
  open: boolean;
  settings: AppSettings | null;
  models: string[];
  loadingModels: boolean;
  onClose: () => void;
  onSave: (payload: AppSettingsUpdate) => Promise<void>;
  onLoadModels: () => Promise<string[]>;
}

export function SettingsModal({
  open,
  settings,
  models,
  loadingModels,
  onClose,
  onSave,
  onLoadModels
}: SettingsModalProps) {
  const [formState, setFormState] = useState({
    openai_api_key: "",
    github_token: "",
    openai_base_url: "",
    model_name: "",
    clone_root: ""
  });
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [autoLoadingModels, setAutoLoadingModels] = useState(false);
  const autoLoadAttemptKeyRef = useRef("");

  useEffect(() => {
    if (!settings || !open) {
      return;
    }
    setFormState({
      openai_api_key: settings.openai_api_key,
      github_token: settings.github_token,
      openai_base_url: settings.openai_base_url,
      model_name: settings.model_name,
      clone_root: settings.clone_root
    });
    setErrorMessage(null);
  }, [settings, open]);

  useEffect(() => {
    const configKey = `${settings?.openai_api_key ?? ""}|${settings?.openai_base_url ?? ""}`;
    if (
      !open ||
      !settings?.openai_api_key_set ||
      !configKey ||
      autoLoadAttemptKeyRef.current === configKey ||
      loadingModels ||
      autoLoadingModels
    ) {
      return;
    }

    let cancelled = false;
    async function loadModelsFromEnv() {
      try {
        autoLoadAttemptKeyRef.current = configKey;
        setAutoLoadingModels(true);
        setErrorMessage(null);
        const loadedModels = await onLoadModels();
        if (!cancelled && loadedModels.length > 0) {
          setFormState((current) => ({
            ...current,
            model_name: current.model_name || loadedModels[0]
          }));
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : "自动获取模型列表失败");
        }
      } finally {
        setAutoLoadingModels(false);
      }
    }

    void loadModelsFromEnv();
    return () => {
      cancelled = true;
    };
  }, [
    open,
    settings?.openai_api_key_set,
    settings?.openai_api_key,
    settings?.openai_base_url,
    loadingModels,
    onLoadModels
  ]);

  if (!open) {
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setSaving(true);
      setErrorMessage(null);
      await onSave({
        openai_api_key: formState.openai_api_key.trim() || null,
        github_token: formState.github_token.trim() || null,
        openai_base_url: formState.openai_base_url.trim(),
        model_name: formState.model_name.trim(),
        clone_root: formState.clone_root.trim()
      });
      onClose();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "保存设置失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleLoadModels() {
    try {
      setErrorMessage(null);
      await onSave({
        openai_api_key: formState.openai_api_key.trim() || null,
        github_token: formState.github_token.trim() || null,
        openai_base_url: formState.openai_base_url.trim(),
        model_name: formState.model_name.trim(),
        clone_root: formState.clone_root.trim()
      });
      const loadedModels = await onLoadModels();
      if (loadedModels.length > 0) {
        setFormState((current) => ({ ...current, model_name: loadedModels[0] }));
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "获取模型列表失败");
    }
  }

  return (
    <div className="modal-backdrop settings-root-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="settings-modal settings-root-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div className="settings-modal-header">
          <div>
            <h2>设置</h2>
            <p>保存后会写入后端 <code>{settings?.env_path ?? "backend/.env"}</code> 并立即更新当前进程环境。</p>
          </div>
          <button className="modal-close-button" type="button" onClick={onClose} aria-label="关闭设置弹窗">关闭</button>
        </div>

        {errorMessage ? <div className="banner error">{errorMessage}</div> : null}

        <form className="settings-form" onSubmit={handleSubmit}>
          <label>
            <span>OpenAI API Key</span>
            <input
              type="password"
              value={formState.openai_api_key}
              onChange={(event) => setFormState((current) => ({ ...current, openai_api_key: event.target.value }))}
              placeholder="sk-..."
            />
          </label>

          <label>
            <span>OpenAI Base URL</span>
            <input
              value={formState.openai_base_url}
              onChange={(event) => setFormState((current) => ({ ...current, openai_base_url: event.target.value }))}
              placeholder="可选，默认 https://api.openai.com/v1"
            />
          </label>

          <label>
            <span>默认模型</span>
            <div className="settings-inline-control">
              <select
                required
                value={formState.model_name}
                onChange={(event) => setFormState((current) => ({ ...current, model_name: event.target.value }))}
              >
                {models.map((model) => (
                  <option key={model} value={model}>{model}</option>
                ))}
                {formState.model_name && !models.includes(formState.model_name) ? (
                  <option value={formState.model_name}>{formState.model_name}</option>
                ) : null}
              </select>
              <button className="secondary-button" type="button" onClick={() => void handleLoadModels()} disabled={loadingModels || autoLoadingModels}>
                {loadingModels || autoLoadingModels ? "加载中" : "从 API 获取"}
              </button>
            </div>
          </label>

          <label>
            <span>GitHub Token</span>
            <input
              type="password"
              value={formState.github_token}
              onChange={(event) => setFormState((current) => ({ ...current, github_token: event.target.value }))}
              placeholder="github_pat_..."
            />
          </label>

          <label>
            <span>默认 clone 根目录</span>
            <input
              value={formState.clone_root}
              onChange={(event) => setFormState((current) => ({ ...current, clone_root: event.target.value }))}
              placeholder="例如 C:\\code\\agent-repos"
            />
          </label>

          <div className="settings-status-row">
            <span>OpenAI Key：{settings?.openai_api_key_set ? "已设置" : "未设置"}</span>
            <span>GitHub Token：{settings?.github_token_set ? "已设置" : "未设置"}</span>
          </div>

          <div className="settings-actions">
            <button className="primary-button" type="submit" disabled={saving}>{saving ? "保存中" : "保存设置"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
