import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Legend,
  Tooltip
} from "recharts";

import type { EvaluationDimension, MetricScore } from "../../types/task";

interface DimensionData {
  dimension: string;
  current: number;
  compare?: number;
}

interface DimensionRadarChartProps {
  metrics: MetricScore[];
  compareTo?: MetricScore[];
  taskName?: string;
  compareTaskName?: string;
}

export function DimensionRadarChart({
  metrics,
  compareTo,
  taskName = "Current",
  compareTaskName = "Compare"
}: DimensionRadarChartProps) {
  // 按维度聚合分数
  const aggregateByDimension = (metricScores: MetricScore[]): Record<string, number> => {
    const dimensionMap: Record<string, { sum: number; count: number }> = {};

    metricScores.forEach((metric) => {
      if (!dimensionMap[metric.category]) {
        dimensionMap[metric.category] = { sum: 0, count: 0 };
      }
      dimensionMap[metric.category].sum += metric.value;
      dimensionMap[metric.category].count += 1;
    });

    const result: Record<string, number> = {};
    Object.entries(dimensionMap).forEach(([dim, data]) => {
      result[dim] = Math.round((data.sum / data.count) * 100) / 100;
    });

    return result;
  };

  const currentDimensions = aggregateByDimension(metrics);
  const compareDimensions = compareTo ? aggregateByDimension(compareTo) : null;

  // 构建图表数据 - 使用固定的键名而不是 taskName
  const dimensions: EvaluationDimension[] = ["quality", "safety", "performance"];
  const data: DimensionData[] = dimensions.map((dim) => ({
    dimension: dim.charAt(0).toUpperCase() + dim.slice(1),
    current: currentDimensions[dim] ?? 0,
    ...(compareDimensions && { compare: compareDimensions[dim] ?? 0 })
  }));

  const colors = {
    current: "#ca5b27",
    compare: "#5b8dd6"
  };

  return (
    <div className="radar-chart-container">
      <ResponsiveContainer width="100%" height={300}>
        <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
          <PolarGrid stroke="rgba(18, 32, 51, 0.1)" />
          <PolarAngleAxis dataKey="dimension" tick={{ fill: "#5d6b82", fontSize: 12 }} />
          <PolarRadiusAxis angle={90} domain={[0, 1]} tick={{ fill: "#5d6b82", fontSize: 10 }} />
          <Radar
            name={taskName}
            dataKey="current"
            stroke={colors.current}
            fill={colors.current}
            fillOpacity={0.3}
          />
          {compareDimensions && (
            <Radar
              name={compareTaskName}
              dataKey="compare"
              stroke={colors.compare}
              fill={colors.compare}
              fillOpacity={0.2}
            />
          )}
          <Legend />
          <Tooltip
            contentStyle={{
              background: "#fff",
              border: "1px solid rgba(18, 32, 51, 0.1)",
              borderRadius: "8px",
              boxShadow: "0 4px 12px rgba(0, 0, 0, 0.1)"
            }}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
