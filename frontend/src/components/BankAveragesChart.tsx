"use client";

import { GlassCard } from "./GlassCard";
import { formatDate, formatRate } from "@/lib/utils";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type BankAveragesPoint = {
  date: string;
  deposit_avg_12m?: number | null;
  loan_avg?: number | null;
};

function fmtAxisDate(d: string) {
  return formatDate(d);
}

export function BankAveragesChart({
  title,
  data,
}: {
  title: string;
  data: BankAveragesPoint[];
}) {
  const chartData = data.map((p) => ({
    date: fmtAxisDate(p.date),
    deposit: p.deposit_avg_12m ?? null,
    loan: p.loan_avg ?? null,
  }));

  return (
    <GlassCard>
      <h2 className="text-xl font-semibold text-white mb-4">{title}</h2>
      <ResponsiveContainer width="100%" height={360}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
          <XAxis dataKey="date" stroke="rgba(255,255,255,0.6)" style={{ fontSize: "12px" }} />
          <YAxis
            stroke="rgba(255,255,255,0.6)"
            style={{ fontSize: "12px" }}
            domain={["dataMin - 0.2", "dataMax + 0.2"]}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "rgba(15, 23, 42, 0.9)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: "12px",
            }}
            labelStyle={{ color: "rgba(255,255,255,0.8)" }}
            formatter={(value: any, name: any) => {
              const label = name === "deposit" ? "Tiền gửi TB (12T)" : "Cho vay TB";
              return [formatRate(value), label];
            }}
          />
          <Legend
            formatter={(value) => (value === "deposit" ? "Tiền gửi TB (12T)" : "Cho vay TB")}
          />
          <Line
            type="monotone"
            dataKey="deposit"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            name="deposit"
          />
          <Line type="monotone" dataKey="loan" stroke="#f59e0b" strokeWidth={2} dot={false} name="loan" />
        </LineChart>
      </ResponsiveContainer>
      <div className="text-white/40 text-xs mt-2">
        Tiền gửi TB: trung bình mức lãi suất 12T cao nhất ở mỗi ngân hàng (online/tại quầy). Cho vay TB: trung bình
        mức lãi suất vay thấp nhất ở mỗi ngân hàng.
      </div>
    </GlassCard>
  );
}

