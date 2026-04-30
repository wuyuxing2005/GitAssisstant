import type { EvaluationTask } from "../types/task";

interface TaskTableProps {
  tasks: EvaluationTask[];
  selectedTaskId?: string;
  selectedCompareIds: string[];
  onSelectTask: (taskId: string) => void;
  onToggleCompare: (taskId: string) => void;
  onRunTask: (taskId: string) => void;
  onDeleteTask: (taskId: string) => void;
}

const statusTextMap: Record<EvaluationTask["status"], string> = {
  draft: "Draft",
  scheduled: "Scheduled",
  running: "Running",
  completed: "Completed",
  failed: "Failed"
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
  runningTaskId
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
              <th>Compare</th>
              <th>Task</th>
              <th>Agent</th>
              <th>Dataset</th>
              <th>Modes</th>
              <th>Strategy</th>
              <th>Status</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => (
              <tr
                key={task.id}
                className={selectedTaskId === task.id ? "row-selected" : undefined}
                onClick={() => onSelectTask(task.id)}
              >
                <td>
                  <input
                    type="checkbox"
                    checked={selectedCompareIds.includes(task.id)}
                    onChange={() => onToggleCompare(task.id)}
                    onClick={(event) => event.stopPropagation()}
                  />
                </td>
                <td>
                  <strong>{task.name}</strong>
                  <p>{task.description}</p>
                </td>
                <td>{task.config.agent_version}</td>
                <td>{task.config.dataset}</td>
                <td>{task.config.evaluation_modes.join(" / ")}</td>
                <td>{task.config.strategy.label}</td>
                <td>
                  <span className={`status-badge ${task.status}`}>{statusTextMap[task.status]}</span>
                </td>
                <td>{new Date(task.updated_at).toLocaleString()}</td>
                <td>
                  <div className="inline-actions" onClick={(event) => event.stopPropagation()}>
                    <button
                      className="secondary-button"
                      onClick={() => onRunTask(task.id)}
                      disabled={runningTaskId === task.id || task.status === "running"}
                    >
                      {runningTaskId === task.id ? (
                        <span className="loading-spinner">Running...</span>
                      ) : task.status === "running" ? (
                        "Running..."
                      ) : (
                        "Run"
                      )}
                    </button>
                    <button
                      className="ghost-button danger"
                      onClick={() => onDeleteTask(task.id)}
                      disabled={runningTaskId === task.id}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
