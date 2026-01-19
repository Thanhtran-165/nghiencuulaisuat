import { GlassCard } from "./GlassCard";
import { LatestRateItem } from "@/lib/api";

interface DepositTableProps {
  data: LatestRateItem[];
  seriesCode: string;
  termMonths: number;
}

export function DepositTable({ data, seriesCode, termMonths }: DepositTableProps) {
  const seriesLabel = seriesCode === 'deposit_online' ? 'Online' : 'At Counter';

  return (
    <GlassCard>
      <h2 className="text-xl font-semibold text-white mb-4">
        Deposit Rates ({seriesLabel} - {termMonths} months)
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/10">
              <th className="text-left py-3 px-4 text-sm font-medium text-white/60">Bank</th>
              <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Rate (%)</th>
              <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Updated</th>
            </tr>
          </thead>
          <tbody>
            {data.map((item) => (
              <tr key={item.bank_name} className="border-b border-white/5 hover:bg-white/5">
                <td className="py-3 px-4 text-white">{item.bank_name}</td>
                <td className="py-3 px-4 text-right">
                  <span className="text-white font-semibold">
                    {item.rate_pct !== null ? item.rate_pct.toFixed(2) : 'N/A'}
                  </span>
                </td>
                <td className="py-3 px-4 text-right text-sm text-white/40">
                  {new Date(item.scraped_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </GlassCard>
  );
}
