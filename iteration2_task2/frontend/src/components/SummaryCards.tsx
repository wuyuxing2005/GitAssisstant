import { Clipboard, Play, CheckCircle, Settings } from "lucide-react";

interface SummaryCardsProps {
  total: number;
  running: number;
  completed: number;
  customMetrics: number;
}

const cardItems = [
  {
    key: "total",
    label: "任务总数",
    hint: "全部评测任务",
    icon: Clipboard,
    gradient: "linear-gradient(135deg, rgba(249, 115, 22, 0.1), rgba(202, 91, 39, 0.05))",
    color: "#ca5b27"
  },
  {
    key: "running",
    label: "运行中",
    hint: "正在执行的任务",
    icon: Play,
    gradient: "linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(37, 99, 235, 0.05))",
    color: "#2563eb"
  },
  {
    key: "completed",
    label: "已完成",
    hint: "已完成的评测",
    icon: CheckCircle,
    gradient: "linear-gradient(135deg, rgba(34, 197, 94, 0.1), rgba(22, 163, 74, 0.05))",
    color: "#16a34a"
  },
  {
    key: "customMetrics",
    label: "自定义指标",
    hint: "已配置的扩展指标",
    icon: Settings,
    gradient: "linear-gradient(135deg, rgba(168, 85, 247, 0.1), rgba(147, 51, 234, 0.05))",
    color: "#9333ea"
  }
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
      {cardItems.map((item) => {
        const value = valueMap[item.key];
        const isActive = item.key === "running" && value > 0;
        const IconComponent = item.icon;

        return (
          <article
            key={item.key}
            className={`card metric-card ${isActive ? "active" : ""}`}
            style={{
              background: item.gradient,
              borderColor: `${item.color}20`,
            }}
          >
            <div className="metric-card-header">
              <span className="metric-card-icon"><IconComponent size={24} /></span>
              {isActive && <span className="metric-card-pulse"></span>}
            </div>
            <span className="card-label">{item.label}</span>
            <strong className="card-value" style={{ color: item.color }}>
              {value}
            </strong>
            <small className="card-hint">{item.hint}</small>
          </article>
        );
      })}
    </section>
  );
}
