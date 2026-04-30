import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Label
} from "recharts";

import type { EvaluationTimelineEvent } from "../../types/task";

interface TimelineData {
  index: number;
  stage: string;
  duration?: number;
  status: string;
}

interface TimelineProgressProps {
  timeline: EvaluationTimelineEvent[];
}

export function TimelineProgress({ timeline }: TimelineProgressProps) {
  // 将时间线事件转换为图表数据
  const data: TimelineData[] = timeline.map((event, index) => ({
    index,
    stage: event.stage,
    status: event.status,
    duration: index > 0 ? index * 100 : 0 // 模拟持续时间
  }));

  const getStatusColor = (status: string): string => {
    const colors: Record<string, string> = {
      pending: "#fbbf24",
      running: "#3b82f6",
      completed: "#22c55e"
    };
    return colors[status] || "#9ca3af";
  };

  return (
    <div className="timeline-progress-container">
      {/* 进度条可视化 */}
      <div className="timeline-steps">
        {timeline.map((event, index) => (
          <div
            key={index}
            className={`timeline-step ${event.status}`}
          >
            <div className="step-indicator">
              <span className="step-icon">
                {event.status === "completed" ? "✓" : event.status === "running" ? "⟳" : "○"}
              </span>
            </div>
            <div className="step-info">
              <span className="step-stage">{event.stage}</span>
              <span className="step-status">{event.status}</span>
              {event.message && <span className="step-message">{event.message}</span>}
            </div>
            {index < timeline.length - 1 && (
              <div className="step-connector">
                <div className="connector-line" />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 可选的图表展示 */}
      {timeline.length > 1 && (
        <div className="timeline-chart" style={{ marginTop: 20 }}>
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(18, 32, 51, 0.1)" />
              <XAxis
                dataKey="stage"
                tick={{ fill: "#5d6b82", fontSize: 10 }}
                angle={-45}
                textAnchor="end"
                height={60}
              />
              <YAxis hide />
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid rgba(18, 32, 51, 0.1)",
                  borderRadius: "8px"
                }}
              />
              <Line
                type="monotone"
                dataKey="index"
                stroke="#ca5b27"
                strokeWidth={2}
                dot={{ fill: "#ca5b27", r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
