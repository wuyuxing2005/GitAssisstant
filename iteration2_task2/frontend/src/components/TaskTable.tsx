import { useState } from "react";
import { FileText, Clock, PlayCircle, CheckCircle, XCircle, Settings, Trash2, Play } from "lucide-react";
import type { EvaluationTask } from "../types/task";
import { labelDimension, labelMode } from "../utils/labels";

const statusTextMap: Record<EvaluationTask["status"], string> = {
  draft: "草稿",
  scheduled: "已排队",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

const statusConfig: Record<EvaluationTask["status"], { color: string; bg: string; icon: JSX.Element }> = {
  draft: { color: "#6b7280", bg: "rgba(107, 114, 128, 0.1)", icon: <FileText size={14} /> },
  scheduled: { color: "#f59e0b", bg: "rgba(245, 158, 11, 0.1)", icon: <Clock size={14} /> },
  running: { color: "#3b82f6", bg: "rgba(59, 130, 246, 0.1)", icon: <PlayCircle size={14} /> },
  completed: { color: "#16a34a", bg: "rgba(22, 163, 74, 0.1)", icon: <CheckCircle size={14} /> },
  failed: { color: "#dc2626", bg: "rgba(220, 38, 38, 0.1)", icon: <XCircle size={14} /> },
};

interface TaskTableProps {
  tasks: EvaluationTask[];
  selectedTaskId?: string;
  selectedCompareIds: string[];
  onSelectTask: (taskId: string) => void;
  onToggleCompare: (taskId: string) => void;
  onRunTask: (taskId: string) => void;
  onDeleteTask: (taskId: string) => void;
  runningTaskId?: string | null;
}

export function TaskTable({
  tasks,
  selectedTaskId,
  selectedCompareIds,
  onSelectTask,
  onToggleCompare,
  onRunTask,
  onDeleteTask,
  runningTaskId,
}: TaskTableProps) {
  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>评测任务</h2>
          <p>集中管理评测任务的创建、运行、对比和状态维护。</p>
        </div>
      </div>
      <div className="table-wrap">
        <table className="task-table">
          <thead>
            <tr>
              <th style={{ width: "50px" }}>对比</th>
              <th>任务</th>
              <th>数据集</th>
              <th>模式</th>
              <th>维度</th>
              <th>策略</th>
              <th>状态</th>
              <th>更新时间</th>
              <th style={{ width: "180px" }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              const statusCfg = statusConfig[task.status];
              const isSelected = selectedTaskId === task.id;

              return (
                <tr
                  key={task.id}
                  className={isSelected ? "row-selected" : ""}
                  onClick={() => onSelectTask(task.id)}
                >
                  <td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      className="compare-checkbox"
                      checked={selectedCompareIds.includes(task.id)}
                      onChange={() => onToggleCompare(task.id)}
                    />
                  </td>
                  <td>
                    <div className="task-name-cell">
                      <strong>{task.name}</strong>
                      {task.config.custom_metrics.length > 0 && (
                        <span className="custom-metric-badge" title={`${task.config.custom_metrics.length} 个自定义指标`}>
                          <Settings size={14} style={{ display: "inline", marginRight: "4px" }} />
                          {task.config.custom_metrics.length}
                        </span>
                      )}
                    </div>
                    <p className="task-description">{task.description || "—"}</p>
                  </td>
                  <td>
                    <span className="dataset-name">{task.config.dataset}</span>
                  </td>
                  <td>
                    <div className="mode-tags">
                      {task.config.evaluation_modes.map((mode) => (
                        <span key={mode} className="mode-tag">{labelMode(mode)}</span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <div className="mode-tags">
                      {task.config.dimensions.map((dimension) => (
                        <span key={dimension} className={`category-badge ${dimension}`}>{labelDimension(dimension)}</span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <span className="strategy-name">{task.config.strategy.label}</span>
                  </td>
                  <td>
                    <span
                      className="status-badge"
                      style={{
                        color: statusCfg.color,
                        background: statusCfg.bg,
                      }}
                    >
                      <span className="status-icon">{statusCfg.icon}</span>
                      {statusTextMap[task.status]}
                    </span>
                  </td>
                  <td>
                    <span className="timestamp">
                      {new Date(task.updated_at).toLocaleString()}
                    </span>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="inline-actions">
                      <button
                        className={runningTaskId === task.id || task.status === "running" ? "action-btn run-btn running" : "action-btn run-btn"}
                        onClick={() => onRunTask(task.id)}
                        disabled={runningTaskId === task.id || task.status === "running"}
                        title="运行该任务"
                      >
                        {runningTaskId === task.id || task.status === "running" ? (
                          <span className="spinner">⟳</span>
                        ) : (
                          <>
                            <Play size={14} />
                            运行
                          </>
                        )}
                      </button>
                      <button
                        className="action-btn delete-btn"
                        onClick={() => onDeleteTask(task.id)}
                        disabled={runningTaskId === task.id}
                        title="删除该任务"
                      >
                        <Trash2 size={14} />
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {tasks.length === 0 && (
          <div className="empty-state">
            <p>暂无评测任务。</p>
            <p className="empty-state-hint">创建第一个评测任务后即可开始。</p>
          </div>
        )}
      </div>
    </section>
  );
}
