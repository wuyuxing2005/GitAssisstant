import { useState, useEffect } from "react";

import type { MetricDefinition } from "../types/task";

interface JudgePromptConfig {
  key: string;
  name: string;
  description: string;
  prompt: string;
  criteria: Record<string, string>;
}

interface PromptEditorProps {
  metric: MetricDefinition;
  onChange: (metric: MetricDefinition) => void;
}

export function PromptEditor({ metric, onChange }: PromptEditorProps) {
  const [templates, setTemplates] = useState<JudgePromptConfig[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string>("default");
  const [customPrompt, setCustomPrompt] = useState("");
  const [customCriteria, setCustomCriteria] = useState<Record<string, string>>({});
  const [newCriteriaKey, setNewCriteriaKey] = useState("");
  const [newCriteriaValue, setNewCriteriaValue] = useState("");
  const [showEditor, setShowEditor] = useState(false);

  // 加载可用的提示词模板
  useEffect(() => {
    fetch("/api/metadata/judge-prompts")
      .then((res) => res.json())
      .then((data) => {
        setTemplates(data);
        if (data.length > 0) {
          setSelectedTemplate(data[0].key);
          const template = data.find((t: JudgePromptConfig) => t.key === data[0].key);
          if (template) {
            setCustomCriteria(template.criteria);
          }
        }
      })
      .catch(console.error);
  }, []);

  // 当模板改变时，更新 criteria
  useEffect(() => {
    const template = templates.find((t) => t.key === selectedTemplate);
    if (template) {
      setCustomCriteria({ ...template.criteria });
      setCustomPrompt("");
    }
  }, [selectedTemplate, templates]);

  // 保存提示词配置到 metric
  useEffect(() => {
    const updatedMetric: MetricDefinition = {
      ...metric,
      judge_prompt: {
        template_key: selectedTemplate,
        custom_prompt: customPrompt || undefined,
        criteria: customCriteria
      }
    };
    onChange(updatedMetric);
  }, [selectedTemplate, customPrompt, customCriteria]);

  const handleAddCriteria = () => {
    if (newCriteriaKey && newCriteriaValue) {
      setCustomCriteria((prev) => ({
        ...prev,
        [newCriteriaKey]: newCriteriaValue
      }));
      setNewCriteriaKey("");
      setNewCriteriaValue("");
    }
  };

  const handleRemoveCriteria = (key: string) => {
    setCustomCriteria((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  return (
    <div className="prompt-editor">
      <div className="prompt-editor-header">
        <label>
          <input
            type="checkbox"
            checked={showEditor}
            onChange={(e) => setShowEditor(e.target.checked)}
          />
          {" "}配置自定义 Judge 提示词
        </label>
      </div>

      {showEditor && (
        <div className="prompt-editor-body">
          <div className="form-row">
            <label style={{ flex: 1 }}>
              选择预设模板
              <select
                value={selectedTemplate}
                onChange={(e) => setSelectedTemplate(e.target.value)}
              >
                {templates.map((template) => (
                  <option key={template.key} value={template.key}>
                    {template.name} - {template.description}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label>
            自定义提示词（可选，留空则使用模板）
            <textarea
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
              rows={6}
              placeholder="使用 {user_input}, {response}, {reference}, {criteria} 等变量"
            />
          </label>

          <div className="criteria-section">
            <h4>评估标准</h4>
            <div className="criteria-list">
              {Object.entries(customCriteria).map(([key, value]) => (
                <div key={key} className="criteria-item">
                  <div className="criteria-item-content">
                    <strong>{key}</strong>
                    <span>{value}</span>
                  </div>
                  <button
                    type="button"
                    className="remove-criteria-btn"
                    onClick={() => handleRemoveCriteria(key)}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>

            <div className="add-criteria-form">
              <input
                placeholder="标准名称 (如：accuracy)"
                value={newCriteriaKey}
                onChange={(e) => setNewCriteriaKey(e.target.value)}
              />
              <input
                placeholder="标准描述"
                value={newCriteriaValue}
                onChange={(e) => setNewCriteriaValue(e.target.value)}
              />
              <button
                type="button"
                className="secondary-button"
                onClick={handleAddCriteria}
              >
                添加
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
