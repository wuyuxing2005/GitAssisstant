import type { EvaluationTask } from "../types/task";

interface TaskTableProps {
  tasks: EvaluationTask[];
}

const statusTextMap: Record<EvaluationTask["status"], string> = {
  draft: "草稿",
  scheduled: "已调度",
  running: "执行中",
  completed: "已完成",
  failed: "失败"
};

export function TaskTable({ tasks }: TaskTableProps) {
  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>评测任务列表</h2>
          <p>预留任务增删改查、状态展示、结果跳转入口。</p>
        </div>
        <button className="primary-button">新建评测任务</button>
      </div>
      <table className="task-table">
        <thead>
          <tr>
            <th>任务名称</th>
            <th>Agent 版本</th>
            <th>数据集</th>
            <th>评测策略</th>
            <th>状态</th>
            <th>更新时间</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.id}>
              <td>
                <strong>{task.name}</strong>
                <p>{task.description}</p>
              </td>
              <td>{task.config.agentVersion}</td>
              <td>{task.config.dataset}</td>
              <td>{task.config.strategy}</td>
              <td>
                <span className={`status-badge ${task.status}`}>
                  {statusTextMap[task.status]}
                </span>
              </td>
              <td>{task.updatedAt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
