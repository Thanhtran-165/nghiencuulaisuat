"use client";

import { GlassCard } from "./GlassCard";
import { formatCurrency, formatDate } from "@/lib/utils";

interface LoanScheduleItem {
  period: number;
  dueDate: string;
  beginningBalance: number;
  principal: number;
  interest: number;
  totalPayment: number;
  endingBalance: number;
  daysInPeriod: number;
}

interface DepositScheduleItem {
  period: number;
  date: string;
  beginningBalance: number;
  interest: number;
  cashflow: number;
  endingBalance: number;
  daysInPeriod: number;
  notes?: string;
}

interface ScheduleTableProps<T> {
  data: T[];
  type: 'loan' | 'deposit';
}

export default function ScheduleTable<T extends LoanScheduleItem | DepositScheduleItem>({
  data,
  type
}: ScheduleTableProps<T>) {
  if (type === 'loan') {
    const loanData = data as LoanScheduleItem[];

    return (
      <GlassCard className="overflow-x-auto">
        <h3 className="text-xl font-semibold text-white mb-4">Lịch trả nợ</h3>
        <div className="min-w-[900px]">
          <table className="w-full">
            <thead>
              <tr className="bg-white/5">
                <th className="px-4 py-3 text-left text-sm font-semibold text-white/90">Kỳ</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-white/90">Ngày đến hạn</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Dư nợ đầu kỳ</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Gốc</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Lãi</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Tổng trả</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Dư nợ cuối kỳ</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Số ngày tính lãi</th>
              </tr>
            </thead>
            <tbody>
              {loanData.map((item, index) => (
                <tr key={item.period} className="border-b border-white/5 hover:bg-white/5">
                  <td className="px-4 py-3 text-sm text-white/80">{item.period}</td>
                  <td className="px-4 py-3 text-sm text-white/80">{formatDate(item.dueDate)}</td>
                  <td className="px-4 py-3 text-sm text-white/80 text-right font-mono">
                    {formatCurrency(item.beginningBalance)}
                  </td>
                  <td className="px-4 py-3 text-sm text-white/80 text-right font-mono">
                    {formatCurrency(item.principal)}
                  </td>
                  <td className="px-4 py-3 text-sm text-white/80 text-right font-mono">
                    {formatCurrency(item.interest)}
                  </td>
                  <td className="px-4 py-3 text-sm text-white/80 text-right font-mono font-semibold">
                    {formatCurrency(item.totalPayment)}
                  </td>
                  <td className="px-4 py-3 text-sm text-white/80 text-right font-mono">
                    {formatCurrency(item.endingBalance)}
                  </td>
                  <td className="px-4 py-3 text-sm text-white/80 text-right">{item.daysInPeriod}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    );
  }

  // type === 'deposit'
  const depositData = data as DepositScheduleItem[];

  return (
    <GlassCard className="overflow-x-auto">
      <h3 className="text-xl font-semibold text-white mb-4">Lịch dòng tiền</h3>
      <div className="min-w-[1000px]">
        <table className="w-full">
          <thead>
            <tr className="bg-white/5">
              <th className="px-4 py-3 text-left text-sm font-semibold text-white/90">Kỳ</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-white/90">Ngày</th>
              <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Số dư đầu kỳ</th>
              <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Lãi kỳ này</th>
              <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Dòng tiền nhận</th>
              <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Số dư cuối kỳ</th>
              <th className="px-4 py-3 text-right text-sm font-semibold text-white/90">Số ngày tính lãi</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-white/90">Ghi chú</th>
            </tr>
          </thead>
          <tbody>
            {depositData.map((item, index) => (
              <tr key={item.period} className="border-b border-white/5 hover:bg-white/5">
                <td className="px-4 py-3 text-sm text-white/80">{item.period}</td>
                <td className="px-4 py-3 text-sm text-white/80">{formatDate(item.date)}</td>
                <td className="px-4 py-3 text-sm text-white/80 text-right font-mono">
                  {formatCurrency(item.beginningBalance)}
                </td>
                <td className="px-4 py-3 text-sm text-white/80 text-right font-mono text-green-400">
                  {formatCurrency(item.interest)}
                </td>
                <td className="px-4 py-3 text-sm text-white/80 text-right font-mono font-semibold">
                  {formatCurrency(item.cashflow)}
                </td>
                <td className="px-4 py-3 text-sm text-white/80 text-right font-mono">
                  {formatCurrency(item.endingBalance)}
                </td>
                <td className="px-4 py-3 text-sm text-white/80 text-right">{item.daysInPeriod}</td>
                <td className="px-4 py-3 text-sm text-white/60">{item.notes || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </GlassCard>
  );
}
