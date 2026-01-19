import { GlassCard } from "./GlassCard";
import { HistoryPoint } from "@/lib/api";
import { formatRate } from "@/lib/utils";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface HistoryChartProps {
  data: HistoryPoint[];
  title: string;
  type: "deposit" | "loan";
}

export function HistoryChart({ data, title, type }: HistoryChartProps) {
  // Format data for chart
  const chartData = data.map((point) => ({
    date: new Date(point.scraped_at).toLocaleDateString("vi-VN"),
    rate: point.rate_pct,
    min: point.rate_min_pct,
    max: point.rate_max_pct,
  }));

  return (
    <GlassCard>
      <h2 className="text-xl font-semibold text-white mb-4">{title}</h2>
      <ResponsiveContainer width="100%" height={400}>
        {type === "deposit" ? (
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis
              dataKey="date"
              stroke="rgba(255,255,255,0.6)"
              style={{ fontSize: '12px' }}
            />
            <YAxis
              stroke="rgba(255,255,255,0.6)"
              style={{ fontSize: '12px' }}
              domain={["dataMin - 0.1", "dataMax + 0.1"]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(15, 23, 42, 0.9)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "12px",
              }}
              labelStyle={{ color: "rgba(255,255,255,0.8)" }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="rate"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ fill: "#3b82f6", strokeWidth: 2, r: 4 }}
              activeDot={{ r: 6 }}
              name="Lãi suất (%)"
            />
          </LineChart>
        ) : (
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis
              dataKey="date"
              stroke="rgba(255,255,255,0.6)"
              style={{ fontSize: '12px' }}
            />
            <YAxis
              stroke="rgba(255,255,255,0.6)"
              style={{ fontSize: '12px' }}
              domain={["dataMin - 0.5", "dataMax + 0.5"]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(15, 23, 42, 0.9)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "12px",
              }}
              labelStyle={{ color: "rgba(255,255,255,0.8)" }}
            />
            <Legend />
            <Area
              type="monotone"
              dataKey="min"
              stackId="1"
              stroke="#22c55e"
              fill="#22c55e"
              fillOpacity={0.3}
              name="Tối thiểu (%)"
            />
            <Area
              type="monotone"
              dataKey="max"
              stackId="1"
              stroke="#ef4444"
              fill="#ef4444"
              fillOpacity={0.3}
              name="Tối đa (%)"
            />
          </AreaChart>
        )}
      </ResponsiveContainer>
    </GlassCard>
  );
}
