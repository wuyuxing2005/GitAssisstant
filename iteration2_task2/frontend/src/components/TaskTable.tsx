import type { EvaluationTask, TaskStatus } from "../types/task";

interface TaskTableProps {
  tasks: EvaluationTask[];
  selectedTaskId?: string;
  selectedCompareIds: string[];
  onSelectTask: (taskId: string) => void;
  onToggleCompare: (taskId: string) => void;
  onRunTask: (taskId: string) => void;
  onChangeStatus: (taskId: string, status: TaskStatus) => void;
  onDeleteTask: (taskId: string) => void;
}

const statusTextMap: Record<EvaluationTask["status"], string> = {
  draft: "Draft",
  scheduled: "Scheduled",
  running: "Running",
  completed: "Completed",
  failed: "Failed"
};

const nextStatusOptions: TaskStatus[] = ["draft", "scheduled", "running", "completed", "failed"];

export function TaskTable({
  tasks,
  selectedTaskId,
  selectedCompareIds,
  onSelectTask,
  onToggleCompare,
  onRunTask,
  onChangeStatus,
  onDeleteTask
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
                    <button className="secondary-button" onClick={() => onRunTask(task.id)}>
                      Run
                    </button>
                    <select
                      value={task.status}
                      onChange={(event) =>
                        onChangeStatus(task.id, event.target.value as TaskStatus)
                      }
                    >
                      {nextStatusOptions.map((status) => (
                        <option key={status} value={status}>
                          {statusTextMap[status]}
                        </option>
                      ))}
                    </select>
                    <button className="ghost-button danger" onClick={() => onDeleteTask(task.id)}>
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
