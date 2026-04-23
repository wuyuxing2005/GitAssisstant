interface SummaryCardsProps {
  total: number;
  running: number;
  completed: number;
  failed: number;
}

const cardItems = [
  { key: "total", label: "任务总数" },
  { key: "running", label: "执行中 / 排队中" },
  { key: "completed", label: "已完成任务" },
  { key: "failed", label: "失败任务" }
] as const;

export function SummaryCards(props: SummaryCardsProps) {
  const valueMap = {
    total: props.total,
    running: props.running,
    completed: props.completed,
    failed: props.failed
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
