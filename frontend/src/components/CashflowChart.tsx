"use client";

import { GlassCard } from "./GlassCard";
import { formatCurrency } from "@/lib/utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

interface CashflowChartProps {
  data: Array<{ period: number; principal?: number; interest: number; total: number }>;
  type: 'loan' | 'deposit';
}

export default function CashflowChart({ data, type }: CashflowChartProps) {
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-slate-900/90 backdrop-blur-sm border border-white/10 rounded-lg p-3">
          <p className="text-white/80 text-sm mb-2">Kỳ {label}</p>
          {payload.map((entry: any, index: number) => (
            <p key={index} className="text-sm" style={{ color: entry.color }}>
              {entry.name}: {formatCurrency(entry.value)}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  if (type === 'loan') {
    return (
      <GlassCard>
        <h3 className="text-xl font-semibold text-white mb-4">Biểu đồ dòng tiền trả nợ</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data}>
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
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ color: 'rgba(255,255,255,0.8)' }}
              formatter={(value) => <span style={{ color: 'rgba(255,255,255,0.8)' }}>{value}</span>}
            />
            <Bar dataKey="principal" name="Gốc" stackId="a" fill="#22c55e" />
            <Bar dataKey="interest" name="Lãi" stackId="a" fill="#3b82f6" />
          </BarChart>
        </ResponsiveContainer>
      </GlassCard>
    );
  }

  // type === 'deposit'
  const depositData = data.map(item => ({
    period: item.period,
    cashflow: item.total
  }));

  return (
    <GlassCard>
      <h3 className="text-xl font-semibold text-white mb-4">Biểu đồ dòng tiền nhận</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={depositData}>
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
          />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="cashflow" name="Dòng tiền" fill="#a855f7" />
        </BarChart>
      </ResponsiveContainer>
    </GlassCard>
  );
}
