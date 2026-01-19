"use client";

import { useState, useEffect } from "react";
import { GlassCard } from "./GlassCard";
import { formatCurrency, formatRate, formatDate } from "@/lib/utils";
import CashflowChart from "./CashflowChart";
import BalanceChart from "./BalanceChart";
import ScheduleTable from "./ScheduleTable";
import { RateSourceSelector, RateMetadata } from "./RateSourceSelector";

interface DepositInput {
  principal: number;
  annualRate: number;
  nMonths: number;
  startDate: string;
  dayCountMode: 'actual_365' | 'estimated';
  interestPayment: 'end' | 'monthly' | 'quarterly' | 'discount' | 'compound';
  earlyWithdrawal: boolean;
  earlyWithdrawalDate?: string;
  nonTermRate?: number;
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

interface DepositOutput {
  totalInterest: number;
  finalValue: number;
  firstInterest: number;
  schedule: DepositScheduleItem[];
  cashflowData: Array<{ period: number; principal?: number; interest: number; total: number }>;
  balanceData: Array<{ period: number; balance: number }>;
}

export default function DepositCalculator() {
  const [formData, setFormData] = useState<DepositInput>({
    principal: 100000000,
    annualRate: 6,
    nMonths: 12,
    startDate: new Date().toISOString().split('T')[0],
    dayCountMode: 'actual_365',
    interestPayment: 'end',
    earlyWithdrawal: false,
    earlyWithdrawalDate: '',
    nonTermRate: 0.5
  });

  const [result, setResult] = useState<DepositOutput | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rateFromBank, setRateFromBank] = useState<number | null>(null);
  const [rateMetadata, setRateMetadata] = useState<RateMetadata | null>(null);

  const handleInputChange = (field: keyof DepositInput, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setError(null);
  };

  // Update annual rate when rate from bank changes
  useEffect(() => {
    if (rateFromBank !== null) {
      setFormData(prev => ({ ...prev, annualRate: rateFromBank }));
    }
  }, [rateFromBank]);

  const handleRateChange = (rate: number | null, metadata: RateMetadata | null) => {
    setRateFromBank(rate);
    setRateMetadata(metadata);
    if (rate !== null) {
      setFormData(prev => ({ ...prev, annualRate: rate }));
    }
  };

  const loadExample = (scenario: number) => {
    const examples: Record<number, DepositInput> = {
      1: {
        principal: 500000000,
        annualRate: 6.5,
        nMonths: 12,
        startDate: new Date().toISOString().split('T')[0],
        dayCountMode: 'actual_365',
        interestPayment: 'monthly',
        earlyWithdrawal: false,
        earlyWithdrawalDate: '',
        nonTermRate: 0.5
      },
      2: {
        principal: 200000000,
        annualRate: 7,
        nMonths: 6,
        startDate: new Date().toISOString().split('T')[0],
        dayCountMode: 'actual_365',
        interestPayment: 'compound',
        earlyWithdrawal: false,
        earlyWithdrawalDate: '',
        nonTermRate: 0.5
      },
      3: {
        principal: 1000000000,
        annualRate: 8,
        nMonths: 24,
        startDate: new Date().toISOString().split('T')[0],
        dayCountMode: 'actual_365',
        interestPayment: 'end',
        earlyWithdrawal: true,
        earlyWithdrawalDate: new Date(Date.now() + 6 * 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        nonTermRate: 0.5
      }
    };

    setFormData(examples[scenario]);
    setResult(null);
    setError(null);
  };

  const calculate = async () => {
    setLoading(true);
    setError(null);

    try {
      // Giả lập tính toán - trong thực tế sẽ gọi API
      await new Promise(resolve => setTimeout(resolve, 1000));

      const schedule: DepositScheduleItem[] = [];
      const cashflowData: Array<{ period: number; principal?: number; interest: number; total: number }> = [];
      const balanceData: Array<{ period: number; balance: number }> = [];

      let balance = formData.principal;
      const monthlyRate = formData.annualRate / 100 / 12;

      for (let i = 1; i <= formData.nMonths; i++) {
        const interest = balance * monthlyRate;
        let cashflow = 0;
        let notes = '';

        if (formData.interestPayment === 'monthly') {
          cashflow = interest;
          notes = 'Nhận lãi tháng';
        } else if (formData.interestPayment === 'quarterly' && i % 3 === 0) {
          cashflow = interest * 3;
          notes = 'Nhận lãi quý';
        } else if (formData.interestPayment === 'discount' && i === 1) {
          cashflow = balance + interest;
          notes = 'Nhận trả trước';
          balance = 0;
        } else if (formData.interestPayment === 'compound') {
          balance += interest;
          notes = 'Lãi nhập gốc';
        } else if (formData.interestPayment === 'end' && i === formData.nMonths) {
          cashflow = balance + interest;
          notes = 'Nhận cuối kỳ';
          balance = 0;
        }

        const date = new Date(formData.startDate);
        date.setMonth(date.getMonth() + i);

        schedule.push({
          period: i,
          date: date.toISOString().split('T')[0],
          beginningBalance: formData.interestPayment === 'compound' ? balance - interest : balance,
          interest,
          cashflow,
          endingBalance: balance,
          daysInPeriod: 30,
          notes
        });

        cashflowData.push({
          period: i,
          interest,
          total: cashflow
        });

        balanceData.push({
          period: i,
          balance
        });
      }

      const totalInterest = schedule.reduce((sum, item) => sum + item.interest, 0);
      const finalValue = schedule[schedule.length - 1]?.endingBalance || formData.principal;
      const firstInterest = schedule[0]?.interest || 0;

      setResult({
        totalInterest,
        finalValue,
        firstInterest,
        schedule,
        cashflowData,
        balanceData
      });

    } catch (err) {
      setError("Có lỗi xảy ra khi tính toán. Vui lòng thử lại.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Input Form */}
      <GlassCard>
        <h2 className="text-2xl font-bold text-white mb-6">Máy tính tiền gửi</h2>

        <div className="space-y-4">
          {/* Số tiền gửi */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Số tiền gửi (VND) <span className="text-red-400">*</span>
            </label>
            <input
              type="number"
              value={formData.principal}
              onChange={(e) => handleInputChange('principal', Number(e.target.value))}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
              placeholder="Nhập số tiền gửi"
            />
          </div>

          {/* Lãi suất năm - Rate Source Selector */}
          <div className="space-y-4">
            <RateSourceSelector
              context="deposit"
              onRateChange={handleRateChange}
            />

            {/* Manual Rate Input */}
            {rateMetadata === null && (
              <div>
                <label className="block text-sm text-white/70 mb-1">
                  Lãi suất năm (%/năm) <span className="text-red-400">*</span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.annualRate}
                  onChange={(e) => handleInputChange('annualRate', Number(e.target.value))}
                  className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
                  placeholder="Nhập lãi suất"
                />
              </div>
            )}

            {/* Rate Display from Bank */}
            {rateMetadata !== null && (
              <div>
                <label className="block text-sm text-white/70 mb-1">
                  Lãi suất năm (%/năm)
                </label>
                <div className="w-full px-4 py-2 rounded-lg glass-input bg-white/5 text-white font-semibold">
                  {formData.annualRate.toFixed(2)}%
                </div>
              </div>
            )}
          </div>

          {/* Kỳ hạn */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Kỳ hạn (tháng) <span className="text-red-400">*</span>
            </label>
            <input
              type="number"
              min="1"
              value={formData.nMonths}
              onChange={(e) => handleInputChange('nMonths', Number(e.target.value))}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
              placeholder="Nhập số tháng"
            />
          </div>

          {/* Ngày bắt đầu */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Ngày bắt đầu <span className="text-red-400">*</span>
            </label>
            <input
              type="date"
              value={formData.startDate}
              onChange={(e) => handleInputChange('startDate', e.target.value)}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
            />
          </div>

          {/* Chế độ tính lãi */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Chế độ tính lãi <span className="text-red-400">*</span>
            </label>
            <select
              value={formData.dayCountMode}
              onChange={(e) => handleInputChange('dayCountMode', e.target.value)}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
            >
              <option value="actual_365">Chuẩn ngân hàng (Actual/365)</option>
              <option value="estimated">Ước tính nhanh (r/12)</option>
            </select>
          </div>

          {/* Hình thức nhận lãi */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Hình thức nhận lãi <span className="text-red-400">*</span>
            </label>
            <select
              value={formData.interestPayment}
              onChange={(e) => handleInputChange('interestPayment', e.target.value)}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
            >
              <option value="end">Nhận lãi cuối kỳ</option>
              <option value="monthly">Nhận lãi định kỳ hàng tháng</option>
              <option value="quarterly">Nhận lãi định kỳ hàng quý</option>
              <option value="discount">Nhận lãi trả trước (chiết khấu)</option>
              <option value="compound">Lãi nhập gốc (lãi kép)</option>
            </select>
          </div>

          {/* Mô phỏng rút trước hạn */}
          <div className="flex items-center gap-3 pt-2">
            <input
              type="checkbox"
              id="earlyWithdrawal"
              checked={formData.earlyWithdrawal}
              onChange={(e) => handleInputChange('earlyWithdrawal', e.target.checked)}
              className="w-4 h-4 rounded glass-input"
            />
            <label htmlFor="earlyWithdrawal" className="text-sm text-white/70">
              Mô phỏng rút trước hạn
            </label>
          </div>

          {formData.earlyWithdrawal && (
            <div className="space-y-4 pl-4 border-l-2 border-white/10">
              {/* Ngày rút trước hạn */}
              <div>
                <label className="block text-sm text-white/70 mb-1">
                  Ngày rút trước hạn <span className="text-red-400">*</span>
                </label>
                <input
                  type="date"
                  value={formData.earlyWithdrawalDate || ''}
                  onChange={(e) => handleInputChange('earlyWithdrawalDate', e.target.value)}
                  className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
                />
              </div>

              {/* Lãi suất không kỳ hạn */}
              <div>
                <label className="block text-sm text-white/70 mb-1">
                  Lãi suất không kỳ hạn (%/năm) <span className="text-red-400">*</span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.nonTermRate}
                  onChange={(e) => handleInputChange('nonTermRate', Number(e.target.value))}
                  className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
                  placeholder="Nhập lãi suất không kỳ hạn"
                />
              </div>
            </div>
          )}

          {/* Buttons */}
          <div className="flex gap-3 pt-4">
            <button
              onClick={calculate}
              disabled={loading}
              className="flex-1 px-6 py-3 rounded-lg glass-button text-white font-semibold hover:bg-white/10 disabled:opacity-50"
            >
              {loading ? "Đang tính..." : "Tính toán"}
            </button>
            <button
              onClick={() => loadExample(1)}
              className="px-6 py-3 rounded-lg glass-button text-white hover:bg-white/10"
            >
              Ví dụ
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}
      </GlassCard>

      {/* Output Section */}
      <div className="space-y-6">
        {result && (
          <>
            {/* KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <GlassCard>
                <p className="text-sm text-white/60 mb-1">Tổng lãi nhận được</p>
                <p className="text-xl font-bold text-green-400">{formatCurrency(result.totalInterest)}</p>
              </GlassCard>
              <GlassCard>
                <p className="text-sm text-white/60 mb-1">Giá trị cuối kỳ</p>
                <p className="text-xl font-bold text-blue-400">{formatCurrency(result.finalValue)}</p>
              </GlassCard>
              <GlassCard>
                <p className="text-sm text-white/60 mb-1">Lãi kỳ đầu</p>
                <p className="text-xl font-bold text-yellow-400">{formatCurrency(result.firstInterest)}</p>
              </GlassCard>
            </div>

            {/* Charts */}
            <CashflowChart data={result.cashflowData} type="deposit" />
            <BalanceChart data={result.balanceData} type="deposit" />
          </>
        )}
      </div>

      {/* Schedule Table - Full Width */}
      {result && (
        <div className="lg:col-span-2">
          <ScheduleTable data={result.schedule} type="deposit" />
        </div>
      )}
    </div>
  );
}
