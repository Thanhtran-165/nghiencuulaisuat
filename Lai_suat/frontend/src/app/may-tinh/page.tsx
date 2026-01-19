"use client";

import { useState } from "react";
import { TopTabs } from "@/components/TopTabs";
import { GlassCard } from "@/components/GlassCard";
import LoanCalculator from "@/components/LoanCalculator";
import DepositCalculator from "@/components/DepositCalculator";

type CalculatorTab = "loan" | "deposit";

export default function MayTinhPage() {
  const [activeTab, setActiveTab] = useState<CalculatorTab>("loan");

  return (
    <div>
      <TopTabs />

      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white mb-4">Máy tính tài chính</h1>
        <p className="text-sm text-white/60">
          Mô phỏng dòng tiền khoản vay và tiền gửi theo chuẩn ngân hàng Việt Nam (Actual/365)
        </p>
      </div>

      {/* Calculator Tabs */}
      <GlassCard className="mb-6">
        <div className="flex space-x-1">
          <button
            onClick={() => setActiveTab("loan")}
            className={`px-6 py-3 rounded-lg text-sm font-medium transition-all relative ${
              activeTab === "loan"
                ? "glass-button active text-white bg-white/10"
                : "text-white/60 hover:text-white hover:bg-white/5"
            }`}
          >
            Máy tính khoản vay
          </button>
          <button
            onClick={() => setActiveTab("deposit")}
            className={`px-6 py-3 rounded-lg text-sm font-medium transition-all relative ${
              activeTab === "deposit"
                ? "glass-button active text-white bg-white/10"
                : "text-white/60 hover:text-white hover:bg-white/5"
            }`}
          >
            Máy tính tiền gửi
          </button>
        </div>
      </GlassCard>

      {/* Calculator Content */}
      {activeTab === "loan" ? <LoanCalculator /> : <DepositCalculator />}
    </div>
  );
}
