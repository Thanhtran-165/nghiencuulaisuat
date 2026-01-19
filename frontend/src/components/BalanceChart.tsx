"use client";

import { GlassCard } from "./GlassCard";
import { formatCurrency } from "@/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';

interface BalanceChartProps {
  data: Array<{ period: number; balance: number }>;
  type: 'loan' | 'deposit';
}

export default function BalanceChart({ data, type }: BalanceChartProps) {
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-slate-900/90 backdrop-blur-sm border border-white/10 rounded-lg p-3">
          <p className="text-white/80 text-sm mb-2">Kỳ {label}</p>
          <p className="text-sm" style={{ color: payload[0].color }}>
            {type === 'loan' ? 'Dư nợ: ' : 'Số dư: '}{formatCurrency(payload[0].value)}
          </p>
        </div>
      );
    }
    return null;
  };

  const color = type === 'loan' ? '#ef4444' : '#22c55e';
  const label = type === 'loan' ? 'Dư nợ còn lại (VND)' : 'Số dư (VND)';

  return (
    <GlassCard>
      <h3 className="text-xl font-semibold text-white mb-4">
        {type === 'loan' ? 'Biểu đồ dư nợ' : 'Biểu đồ số dư'}
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
          <XAxis
            dataKey="period"
            stroke="rgba(255,255,255,0.6)"
            tick={{ fill: 'rgba(255,255,255,0.6)', fontSize: 12 }}
            label={{ value: 'Kỳ', position: 'insideBottom', offset: -5, fill: 'rgba(255,255,255,0.6)' }}
          />
          <YAxis
            stroke="rgba(255,255,255,0.6)"
            tick={{ fill: 'rgba(255,255,255,0.6)', fontSize: 12 }}
            tickFormatter={(value) => `${(value / 1000000).toFixed(0)}M`}
            label={{ value: label, angle: -90, position: 'insideLeft', fill: 'rgba(255,255,255,0.6)' }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="balance"
            stroke={color}
            strokeWidth={2}
            dot={{ fill: color, strokeWidth: 2, r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </GlassCard>
  );
}
