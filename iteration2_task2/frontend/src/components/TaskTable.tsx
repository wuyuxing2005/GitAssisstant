import { useState } from "react";
import { FileText, Clock, PlayCircle, CheckCircle, XCircle, Settings, Trash2, Play } from "lucide-react";
import type { EvaluationTask } from "../types/task";

const statusTextMap: Record<EvaluationTask["status"], string> = {
  draft: "Draft",
  scheduled: "Scheduled",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
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
          <h2>Evaluation Tasks</h2>
          <p>Create, schedule, run, compare, and maintain task state in one place.</p>
        </div>
      </div>
      <div className="table-wrap">
        <table className="task-table">
          <thead>
            <tr>
              <th style={{ width: "50px" }}>Compare</th>
              <th>Task</th>
              <th>Agent</th>
              <th>Dataset</th>
              <th>Modes</th>
              <th>Strategy</th>
              <th>Status</th>
              <th>Updated</th>
              <th style={{ width: "180px" }}>Actions</th>
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
                        <span className="custom-metric-badge" title={`${task.config.custom_metrics.length} custom metrics`}>
                          <Settings size={14} style={{ display: "inline", marginRight: "4px" }} />
                          {task.config.custom_metrics.length}
                        </span>
                      )}
                    </div>
                    <p className="task-description">{task.description || "—"}</p>
                  </td>
                  <td>
                    <span className="agent-version">{task.config.agent_version}</span>
                  </td>
                  <td>
                    <span className="dataset-name">{task.config.dataset}</span>
                  </td>
                  <td>
                    <div className="mode-tags">
                      {task.config.evaluation_modes.map((mode) => (
                        <span key={mode} className="mode-tag">{mode}</span>
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
                        title="Run this task"
                      >
                        {runningTaskId === task.id || task.status === "running" ? (
                          <span className="spinner">⟳</span>
                        ) : (
                          <>
                            <Play size={14} />
                            Run
                          </>
                        )}
                      </button>
                      <button
                        className="action-btn delete-btn"
                        onClick={() => onDeleteTask(task.id)}
                        disabled={runningTaskId === task.id}
                        title="Delete this task"
                      >
                        <Trash2 size={14} />
                        Delete
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
            <p>No tasks created yet.</p>
            <p className="empty-state-hint">Create your first evaluation task to get started.</p>
          </div>
        )}
      </div>
    </section>
  );
}
