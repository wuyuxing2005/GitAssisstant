import type { EvaluationTask, MetricScore, RunMode } from "../types/task";
import { formatDisplayTime } from "../utils/time";

interface TaskDetailPageProps {
  task: EvaluationTask | null;
  busyTaskId: string | null;
  onRunTask: (taskId: string, mode: RunMode, reset?: boolean) => Promise<void>;
}

function formatMetric(metric: MetricScore): string {
  const rawValue = Number.isInteger(metric.value) ? metric.value.toString() : metric.value.toFixed(2);
  return metric.unit ? `${rawValue} ${metric.unit}` : rawValue;
}

export function TaskDetailPage({ task, busyTaskId, onRunTask }: TaskDetailPageProps) {
  if (!task) {
    return (
      <section className="card">
        <div className="empty-state">
          <strong>尚未选中任务</strong>
          <p>创建任务或在列表中选择一项后，这里会显示执行状态、计划、工具调用和时间线。</p>
        </div>
      </section>
    );
  }

  const result = task.result;
  const snapshot = result?.current_state;
  const isBusy = busyTaskId === task.id;
  const showSeparateError = !!result?.error_message && result.error_message !== result.summary;

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <h2>任务详情</h2>
          <p>{task.name}</p>
        </div>
        <div className="action-row">
          <button
            className="secondary-button"
            type="button"
            onClick={() => void onRunTask(task.id, "step")}
            disabled={isBusy}
          >
            继续单步
          </button>
          <button
            className="primary-button"
            type="button"
            onClick={() => void onRunTask(task.id, "auto")}
            disabled={isBusy}
          >
            自动执行
          </button>
        </div>
      </div>
      <div className="score-grid">
        {(result?.metrics ?? []).map((metric) => (
          <article key={metric.name} className="score-card">
            <span>{metric.name}</span>
            <strong>{formatMetric(metric)}</strong>
            <small>{metric.description ?? metric.category}</small>
          </article>
        ))}
        {!(result?.metrics?.length ?? 0) ? (
          <article className="score-card">
            <span>尚未执行</span>
            <strong>-</strong>
            <small>任务启动后这里会出现实时汇总指标。</small>
          </article>
        ) : null}
      </div>
      <div className="detail-grid">
        <article>
          <h3>任务配置</h3>
          <dl className="detail-list">
            <div>
              <dt>仓库来源</dt>
              <dd>{task.config.repo_source}</dd>
            </div>
            <div>
              <dt>Issue 输入</dt>
              <dd>{task.config.issue_input}</dd>
            </div>
            <div>
              <dt>运行模式</dt>
              <dd>{task.config.run_mode}</dd>
            </div>
            <div>
              <dt>最大轮数</dt>
              <dd>{task.config.max_iterations}</dd>
            </div>
            {task.config.model_name ? (
              <div>
                <dt>模型名</dt>
                <dd>{task.config.model_name}</dd>
              </div>
            ) : null}
          </dl>
        </article>
        <article>
          <h3>运行状态</h3>
          <dl className="detail-list">
            <div>
              <dt>任务状态</dt>
              <dd>{task.status}</dd>
            </div>
            <div>
              <dt>线程 ID</dt>
              <dd>{snapshot?.thread_id ?? "-"}</dd>
            </div>
            <div>
              <dt>仓库路径</dt>
              <dd>{snapshot?.repo_path ?? "-"}</dd>
            </div>
            <div>
              <dt>当前轮数</dt>
              <dd>{snapshot ? `${snapshot.iteration_count}/${snapshot.max_iterations}` : "-"}</dd>
            </div>
            <div>
              <dt>开始时间</dt>
              <dd>{result?.started_at ? formatDisplayTime(result.started_at) : "-"}</dd>
            </div>
            <div>
              <dt>结束时间</dt>
              <dd>{result?.finished_at ? formatDisplayTime(result.finished_at) : "-"}</dd>
            </div>
          </dl>
        </article>
      </div>
      <div className="detail-grid">
        <article>
          <h3>执行摘要</h3>
          <p className="paragraph-block">{result?.summary ?? "尚未开始执行。"}</p>
          {showSeparateError ? <p className="error-copy">{result.error_message}</p> : null}
          <h3>计划</h3>
          <ul className="bullet-list">
            {(snapshot?.plan ?? []).map((planItem, index) => (
              <li key={`${task.id}-plan-${index}`}>{planItem}</li>
            ))}
            {!(snapshot?.plan?.length ?? 0) ? <li>当前还没有生成计划。</li> : null}
          </ul>
        </article>
        <article>
          <h3>工具使用概览</h3>
          <div className="tool-usage-list">
            {(result?.tool_usage ?? []).map((tool) => (
              <div key={`${task.id}-tool-${tool.name}`} className="metric-row">
                <span>{tool.name}</span>
                <strong>{tool.count}</strong>
              </div>
            ))}
            {!(result?.tool_usage?.length ?? 0) ? <p className="muted-copy">还没有工具调用。</p> : null}
          </div>
          <h3>最新日志</h3>
          <div className="log-list">
            {(result?.logs_preview ?? []).map((logLine, index) => (
              <code key={`${task.id}-log-${index}`}>{logLine}</code>
            ))}
            {!(result?.logs_preview?.length ?? 0) ? <p className="muted-copy">暂无日志。</p> : null}
          </div>
        </article>
      </div>
      <section className="timeline-panel">
        <div className="section-header">
          <div>
            <h3>执行时间线</h3>
            <p>完整展示 planner、react、tools、reflect 四类节点输出。</p>
          </div>
        </div>
        <div className="timeline-list">
          {(result?.timeline ?? []).map((entry) => (
            <article key={entry.id} className="timeline-item">
              <div className="timeline-meta">
                <span className="timeline-node">{entry.node}</span>
                <time>{formatDisplayTime(entry.created_at)}</time>
              </div>
              <strong>{entry.title}</strong>
              {entry.content ? <pre>{entry.content}</pre> : <p className="muted-copy">无文本输出</p>}
              {entry.tool_calls.length > 0 ? (
                <div className="tool-call-list">
                  {entry.tool_calls.map((toolCall, index) => (
                    <div key={`${entry.id}-tool-${index}`} className="tool-call-chip">
                      <strong>{toolCall.name}</strong>
                      <code>{JSON.stringify(toolCall.args)}</code>
                    </div>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
          {!(result?.timeline?.length ?? 0) ? (
            <div className="empty-state inline">
              <strong>暂无执行轨迹</strong>
              <p>点击任务列表中的“单步”或“自动”开始执行。</p>
            </div>
          ) : null}
        </div>
      </section>
    </section>
  );
}
