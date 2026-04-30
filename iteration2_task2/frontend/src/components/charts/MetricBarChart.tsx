import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell
} from "recharts";

import type { MetricScore } from "../../types/task";

interface BarData {
  name: string;
  key: string;
  current: number;
  compare: number | null;
  category: string;
}

interface MetricBarChartProps {
  metrics: MetricScore[];
  compareTo?: MetricScore[];
  taskName?: string;
  compareTaskName?: string;
  maxHeight?: number;
}

export function MetricBarChart({
  metrics,
  compareTo,
  taskName = "Current",
  compareTaskName = "Compare",
  maxHeight = 400
}: MetricBarChartProps) {
  // 构建对比数据的映射
  const compareMap = new Map<string, number>();
  if (compareTo) {
    compareTo.forEach((metric) => {
      compareMap.set(metric.key, metric.value);
    });
  }

  // 构建图表数据
  const chartData: BarData[] = metrics.map((metric) => ({
    name: metric.label,
    key: metric.key,
    current: metric.value,
    compare: compareMap.has(metric.key) ? compareMap.get(metric.key)! : null,
    category: metric.category
  }));

  // 为不同维度设置不同颜色
  const getCategoryColor = (category: string): string => {
    const colors: Record<string, string> = {
      quality: "#ca5b27",
      safety: "#16a34a",
      performance: "#2563eb",
      efficiency: "#9333ea"
    };
    return colors[category] || "#6b7280";
  };

  const hasCompare = compareTo && compareTo.length > 0;

  return (
    <div className="bar-chart-container" style={{ height: maxHeight }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 10, right: 30, left: 20, bottom: 10 }}
          barGap={8}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(18, 32, 51, 0.1)" />
          <XAxis type="number" domain={[0, 1]} tick={{ fill: "#5d6b82", fontSize: 12 }} />
          <YAxis
            type="category"
            dataKey="name"
            width={120}
            tick={{ fill: "#5d6b82", fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{
              background: "#fff",
              border: "1px solid rgba(18, 32, 51, 0.1)",
              borderRadius: "8px",
              boxShadow: "0 4px 12px rgba(0, 0, 0, 0.1)"
            }}
            formatter={(value) => value == null ? "N/A" : Number(value).toFixed(2)}
          />
          <Bar
            dataKey="current"
            name={taskName}
            radius={[0, 4, 4, 0]}
            fill="#ca5b27"
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getCategoryColor(entry.category)} />
            ))}
          </Bar>
          {hasCompare && (
            <Bar
              dataKey="compare"
              name={compareTaskName}
              fill="#93c5fd"
              radius={[0, 4, 4, 0]}
            />
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
