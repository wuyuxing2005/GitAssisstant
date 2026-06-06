import type { EvaluationTask, RunMode } from "../types/task";
import { formatDisplayTime } from "../utils/time";

interface TaskTableProps {
  tasks: EvaluationTask[];
  selectedTaskId: string | null;
  busyTaskId: string | null;
  onSelectTask: (taskId: string) => void;
  onRunTask: (taskId: string, mode: RunMode, reset?: boolean) => Promise<void>;
  onDeleteTask: (taskId: string) => Promise<void>;
}

const statusTextMap: Record<EvaluationTask["status"], string> = {
  draft: "草稿",
  scheduled: "排队中",
  running: "执行中",
  completed: "已完成",
  failed: "失败"
};

export function TaskTable({
  tasks,
  selectedTaskId,
  busyTaskId,
  onSelectTask,
  onRunTask,
  onDeleteTask
}: TaskTableProps) {
  if (tasks.length === 0) {
    return (
      <section className="card">
        <div className="section-header">
          <div>
            <h2>任务列表</h2>
            <p>围绕仓库、Issue 和运行模式管理 gitIssueAssitant 执行任务。</p>
          </div>
        </div>
        <div className="empty-state">
          <strong>还没有任务</strong>
          <p>先创建一个任务，然后从这里自动执行或重置重跑。</p>
        </div>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>任务列表</h2>
          <p>点击行可切换详情，右侧动作可以直接驱动后端运行。</p>
        </div>
        <span className="table-tip">单进程串行执行，运行中无法并发触发其他任务。</span>
      </div>
      <table className="task-table">
        <thead>
          <tr>
            <th>任务</th>
            <th>仓库</th>
            <th>Issue / 模式</th>
            <th>状态</th>
            <th>进度</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => {
            const snapshot = task.result?.current_state;
            const isSelected = task.id === selectedTaskId;
            const isBusy = busyTaskId === task.id;
            const disableActions = Boolean(busyTaskId && busyTaskId !== task.id);

            return (
              <tr
                key={task.id}
                className={isSelected ? "selected" : undefined}
                onClick={() => onSelectTask(task.id)}
              >
                <td>
                  <strong>{task.name}</strong>
                  <p>{task.description || "未填写任务说明"}</p>
                </td>
                <td>
                  <code>{task.config.repo_source}</code>
                  {task.config.target_dir ? <p>目录：{task.config.target_dir}</p> : null}
                </td>
                <td>
                  <p className="compact-copy">{task.config.issue_input}</p>
                  <small className="meta-inline">模式：{task.config.run_mode}</small>
                </td>
                <td>
                  <span className={`status-badge ${task.status}`}>
                    {statusTextMap[task.status]}
                  </span>
                </td>
                <td>
                  {snapshot ? (
                    <span>{snapshot.iteration_count}</span>
                  ) : (
                    <span>-</span>
                  )}
                </td>
                <td>{formatDisplayTime(task.updated_at)}</td>
                <td>
                  <div className="action-row">
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void onRunTask(task.id, "auto");
                      }}
                      disabled={disableActions || isBusy}
                    >
                      自动
                    </button>
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void onRunTask(task.id, "auto", true);
                      }}
                      disabled={disableActions || isBusy}
                    >
                      重跑
                    </button>
                    <button
                      className="ghost-button danger"
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void onDeleteTask(task.id);
                      }}
                      disabled={disableActions || isBusy}
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
