import { GlassCard } from "./GlassCard";
import { LatestRateItem } from "@/lib/api";

interface LoanTableProps {
  data: LatestRateItem[];
  seriesCode: string;
}

export function LoanTable({ data, seriesCode }: LoanTableProps) {
  const seriesLabel = seriesCode === 'loan_the_chap' ? 'Secured' : 'Unsecured';

  return (
    <GlassCard>
      <h2 className="text-xl font-semibold text-white mb-4">
        Loan Rates ({seriesLabel})
      </h2>
      <p className="text-xs text-white/40 mb-4 italic">
        Nguồn lãi suất vay hiện có: Timo (1 nguồn)
      </p>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/10">
              <th className="text-left py-3 px-4 text-sm font-medium text-white/60">Bank</th>
              <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Min (%)</th>
              <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Max (%)</th>
              <th className="text-right py-3 px-4 text-sm font-medium text-white/60">Updated</th>
            </tr>
          </thead>
          <tbody>
            {data.map((item) => (
              <tr key={item.bank_name} className="border-b border-white/5 hover:bg-white/5">
                <td className="py-3 px-4 text-white">{item.bank_name}</td>
                <td className="py-3 px-4 text-right">
                  <span className="text-green-400 font-semibold">
                    {item.rate_min_pct !== null ? item.rate_min_pct.toFixed(2) : 'N/A'}
                  </span>
                </td>
                <td className="py-3 px-4 text-right">
                  <span className="text-red-400 font-semibold">
                    {item.rate_max_pct !== null ? item.rate_max_pct.toFixed(2) : 'N/A'}
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
