interface SummaryCardsProps {
  total: number;
  running: number;
  completed: number;
  customMetrics: number;
}

const cardItems = [
  { key: "total", label: "评测任务总数" },
  { key: "running", label: "执行中任务" },
  { key: "completed", label: "已完成任务" },
  { key: "customMetrics", label: "自定义指标数" }
] as const;

export function SummaryCards(props: SummaryCardsProps) {
  const valueMap = {
    total: props.total,
    running: props.running,
    completed: props.completed,
    customMetrics: props.customMetrics
  };

  return (
    <section className="summary-grid">
      {cardItems.map((item) => (
        <article key={item.key} className="card metric-card">
          <span className="card-label">{item.label}</span>
          <strong className="card-value">{valueMap[item.key]}</strong>
        </article>
      ))}
    </section>
  );
}
