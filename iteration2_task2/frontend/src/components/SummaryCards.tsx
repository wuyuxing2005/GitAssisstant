interface SummaryCardsProps {
  total: number;
  running: number;
  completed: number;
  customMetrics: number;
}

const cardItems = [
  { key: "total", label: "Tasks", hint: "All evaluation tasks" },
  { key: "running", label: "Running", hint: "Currently executing" },
  { key: "completed", label: "Completed", hint: "Finished runs" },
  { key: "customMetrics", label: "Custom Metrics", hint: "Configured extensions" }
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
          <small className="card-hint">{item.hint}</small>
        </article>
      ))}
    </section>
  );
}
