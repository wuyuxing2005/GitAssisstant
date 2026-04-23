import type { EvaluationTask } from "../types/task";

interface TaskDetailPageProps {
  task: EvaluationTask;
}

export function TaskDetailPage({ task }: TaskDetailPageProps) {
  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>单次评测结果展示</h2>
          <p>{task.name}</p>
        </div>
        <button className="secondary-button">查看对比分析</button>
      </div>
      <div className="score-grid">
        {task.scores.map((score) => (
          <article key={score.name} className="score-card">
            <span>{score.name}</span>
            <strong>{score.value}</strong>
            <small>趋势：{score.trend}</small>
          </article>
        ))}
      </div>
      <div className="detail-grid">
        <article>
          <h3>评测配置</h3>
          <ul>
            <li>Agent 版本：{task.config.agentVersion}</li>
            <li>数据集：{task.config.dataset}</li>
            <li>评测方法：{task.config.evaluationMethods.join(" / ")}</li>
            <li>指标集合：{task.config.metrics.join(", ")}</li>
          </ul>
        </article>
        <article>
          <h3>后续扩展</h3>
          <ul>
            <li>接入真实图表库</li>
            <li>接入任务配置表单</li>
            <li>接入执行日志与中间过程回放</li>
            <li>接入真实后端接口与权限系统</li>
          </ul>
        </article>
      </div>
    </section>
  );
}
