"use client";

import { useState, useEffect } from "react";
import { GlassCard } from "./GlassCard";
import { formatCurrency, formatPercent } from "@/lib/utils";
import CashflowChart from "./CashflowChart";
import BalanceChart from "./BalanceChart";
import ScheduleTable from "./ScheduleTable";
import { RateSourceSelector, RateMetadata } from "./RateSourceSelector";

interface LoanInput {
  principal: number;
  annualRate: number;
  nMonths: number;
  startDate: string;
  paymentDay: number;
  dayCountMode: 'actual_365' | 'estimated';
  paymentMethod: 'principal_equal' | 'annuity' | 'interest_only';
  gracePrincipalMonths: number;
  monthlyIncome: number;
}

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

interface LoanOutput {
  totalInterest: number;
  totalPayment: number;
  firstPayment: number;
  maxPayment: number;
  schedule: LoanScheduleItem[];
  cashflowData: Array<{ period: number; principal: number; interest: number; total: number }>;
  balanceData: Array<{ period: number; balance: number }>;
}

export default function LoanCalculator() {
  const [formData, setFormData] = useState<LoanInput>({
    principal: 100000000,
    annualRate: 12,
    nMonths: 12,
    startDate: new Date().toISOString().split('T')[0],
    paymentDay: new Date().getDate(),
    dayCountMode: 'actual_365',
    paymentMethod: 'annuity',
    gracePrincipalMonths: 0,
    monthlyIncome: 0
  });

  const [result, setResult] = useState<LoanOutput | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rateFromBank, setRateFromBank] = useState<number | null>(null);
  const [rateMetadata, setRateMetadata] = useState<RateMetadata | null>(null);

  const handleInputChange = (field: keyof LoanInput, value: any) => {
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
    const examples: Record<number, LoanInput> = {
      1: {
        principal: 500000000,
        annualRate: 10.5,
        nMonths: 24,
        startDate: new Date().toISOString().split('T')[0],
        paymentDay: new Date().getDate(),
        dayCountMode: 'actual_365',
        paymentMethod: 'annuity',
        gracePrincipalMonths: 0,
        monthlyIncome: 0
      },
      2: {
        principal: 200000000,
        annualRate: 15,
        nMonths: 36,
        startDate: new Date().toISOString().split('T')[0],
        paymentDay: new Date().getDate(),
        dayCountMode: 'actual_365',
        paymentMethod: 'principal_equal',
        gracePrincipalMonths: 6,
        monthlyIncome: 0
      },
      3: {
        principal: 1000000000,
        annualRate: 8,
        nMonths: 60,
        startDate: new Date().toISOString().split('T')[0],
        paymentDay: new Date().getDate(),
        dayCountMode: 'estimated',
        paymentMethod: 'interest_only',
        gracePrincipalMonths: 0,
        monthlyIncome: 0
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

      const schedule: LoanScheduleItem[] = [];
      const cashflowData: Array<{ period: number; principal: number; interest: number; total: number }> = [];
      const balanceData: Array<{ period: number; balance: number }> = [];

      let balance = formData.principal;
      const monthlyRate = formData.annualRate / 100 / 12;

      for (let i = 1; i <= formData.nMonths; i++) {
        const interest = balance * monthlyRate;
        let principal = 0;
        let totalPayment = 0;

        if (formData.paymentMethod === 'annuity') {
          const annuity = formData.principal * monthlyRate * Math.pow(1 + monthlyRate, formData.nMonths) /
            (Math.pow(1 + monthlyRate, formData.nMonths) - 1);
          totalPayment = annuity;
          principal = annuity - interest;
        } else if (formData.paymentMethod === 'principal_equal') {
          principal = formData.principal / formData.nMonths;
          totalPayment = principal + interest;
        } else if (formData.paymentMethod === 'interest_only') {
          if (i === formData.nMonths) {
            principal = balance;
            totalPayment = principal + interest;
          } else {
            totalPayment = interest;
          }
        }

        balance -= principal;
        if (balance < 0) balance = 0;

        const dueDate = new Date(formData.startDate);
        dueDate.setMonth(dueDate.getMonth() + i);

        schedule.push({
          period: i,
          dueDate: dueDate.toISOString().split('T')[0],
          beginningBalance: balance + principal,
          principal,
          interest,
          totalPayment,
          endingBalance: balance,
          daysInPeriod: 30
        });

        cashflowData.push({
          period: i,
          principal,
          interest,
          total: totalPayment
        });

        balanceData.push({
          period: i,
          balance
        });
      }

      const totalInterest = schedule.reduce((sum, item) => sum + item.interest, 0);
      const totalPayment = schedule.reduce((sum, item) => sum + item.totalPayment, 0);
      const firstPayment = schedule[0]?.totalPayment || 0;
      const maxPayment = Math.max(...schedule.map(item => item.totalPayment));

      setResult({
        totalInterest,
        totalPayment,
        firstPayment,
        maxPayment,
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

  const ptiColorClass = (pti: number) => {
    if (!Number.isFinite(pti)) return "text-white";
    if (pti <= 0.3) return "text-green-400";
    if (pti <= 0.4) return "text-yellow-400";
    return "text-red-400";
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Input Form */}
      <GlassCard>
        <h2 className="text-2xl font-bold text-white mb-6">Máy tính khoản vay</h2>

        <div className="space-y-4">
          {/* Số tiền vay */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Số tiền vay (VND) <span className="text-red-400">*</span>
            </label>
            <input
              type="number"
              value={formData.principal}
              onChange={(e) => handleInputChange('principal', Number(e.target.value))}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
              placeholder="Nhập số tiền vay"
            />
          </div>

          {/* Thu nhập hàng tháng (tùy chọn) */}
          <div>
            <label className="block text-sm text-white/70 mb-1">Thu nhập hàng tháng (VND)</label>
            <input
              type="number"
              min="0"
              value={formData.monthlyIncome}
              onChange={(e) => handleInputChange('monthlyIncome', Number(e.target.value))}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
              placeholder="Nhập thu nhập để tính chỉ số an toàn"
            />
            <p className="text-xs text-white/40 mt-1">
              Dùng để tính PTI/DSTI (khoản trả hàng tháng / thu nhập hàng tháng).
            </p>
          </div>

          {/* Lãi suất năm - Rate Source Selector */}
          <div className="space-y-4">
            <RateSourceSelector
              context="loan"
              onRateChange={handleRateChange}
            />
            <p className="text-xs text-white/40 italic">
              Nguồn lãi suất vay hiện có: Timo (1 nguồn)
            </p>

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

          {/* Ngày trả hàng tháng */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Ngày trả hàng tháng (1-31) <span className="text-red-400">*</span>
            </label>
            <input
              type="number"
              min="1"
              max="31"
              value={formData.paymentDay}
              onChange={(e) => handleInputChange('paymentDay', Number(e.target.value))}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
              placeholder="Nhập ngày trả"
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

          {/* Phương thức trả nợ */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Phương thức trả nợ <span className="text-red-400">*</span>
            </label>
            <select
              value={formData.paymentMethod}
              onChange={(e) => handleInputChange('paymentMethod', e.target.value)}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
            >
              <option value="principal_equal">Dư nợ giảm dần – Gốc đều</option>
              <option value="annuity">Trả góp đều – Gốc + lãi gần cố định (Annuity/EMI)</option>
              <option value="interest_only">Chỉ trả lãi hàng tháng, gốc cuối kỳ</option>
            </select>
          </div>

          {/* Ân hạn gốc */}
          <div>
            <label className="block text-sm text-white/70 mb-1">
              Ân hạn gốc (tháng)
            </label>
            <input
              type="number"
              min="0"
              value={formData.gracePrincipalMonths}
              onChange={(e) => handleInputChange('gracePrincipalMonths', Number(e.target.value))}
              className="w-full px-4 py-2 rounded-lg glass-input text-white focus:ring-2 focus:ring-white/20"
              placeholder="Nhập số tháng ân hạn"
            />
          </div>

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
            <div className="grid grid-cols-2 gap-4">
              <GlassCard>
                <p className="text-sm text-white/60 mb-1">Tổng lãi phải trả</p>
                <p className="text-xl font-bold text-yellow-400">{formatCurrency(result.totalInterest)}</p>
              </GlassCard>
              <GlassCard>
                <p className="text-sm text-white/60 mb-1">Tổng tiền phải trả</p>
                <p className="text-xl font-bold text-blue-400">{formatCurrency(result.totalPayment)}</p>
              </GlassCard>
              <GlassCard>
                <p className="text-sm text-white/60 mb-1">Khoản trả kỳ đầu</p>
                <p className="text-xl font-bold text-green-400">{formatCurrency(result.firstPayment)}</p>
              </GlassCard>
              <GlassCard>
                <p className="text-sm text-white/60 mb-1">Khoản trả lớn nhất</p>
                <p className="text-xl font-bold text-red-400">{formatCurrency(result.maxPayment)}</p>
              </GlassCard>
            </div>

            {/* Affordability / Safety Metrics (optional) */}
            {formData.monthlyIncome > 0 && (
              <GlassCard>
                <p className="text-sm text-white/60 mb-4">Chỉ số an toàn trả nợ (tham khảo)</p>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-white/50 mb-1">Thu nhập/tháng</p>
                    <p className="text-lg font-semibold text-white">{formatCurrency(formData.monthlyIncome)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-white/50 mb-1">Dư địa (kỳ lớn nhất)</p>
                    <p className="text-lg font-semibold text-white">
                      {formatCurrency(formData.monthlyIncome - result.maxPayment)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-white/50 mb-1">PTI/DSTI (kỳ đầu)</p>
                    <p className={`text-lg font-semibold ${ptiColorClass(result.firstPayment / formData.monthlyIncome)}`}>
                      {formatPercent(result.firstPayment / formData.monthlyIncome)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-white/50 mb-1">PTI/DSTI (lớn nhất)</p>
                    <p className={`text-lg font-semibold ${ptiColorClass(result.maxPayment / formData.monthlyIncome)}`}>
                      {formatPercent(result.maxPayment / formData.monthlyIncome)}
                    </p>
                  </div>
                </div>
                <p className="text-xs text-white/40 mt-4">
                  Lưu ý: ngưỡng an toàn phụ thuộc ngân hàng/quốc gia và chi phí sinh hoạt, các khoản nợ khác.
                </p>
              </GlassCard>
            )}

            {/* Charts */}
            <CashflowChart data={result.cashflowData} type="loan" />
            <BalanceChart data={result.balanceData} type="loan" />
          </>
        )}
      </div>

      {/* Schedule Table - Full Width */}
      {result && (
        <div className="lg:col-span-2">
          <ScheduleTable data={result.schedule} type="loan" />
        </div>
      )}
    </div>
  );
}
