import { GlassCard } from "./GlassCard";

interface KPICardProps {
  title: string;
  value: string;
  subtitle?: string;
}

function KPICard({ title, value, subtitle }: KPICardProps) {
  return (
    <GlassCard className="flex flex-col">
      <p className="text-sm text-white/60 mb-2">{title}</p>
      <p className="text-3xl font-bold text-white mb-1">{value}</p>
      {subtitle && <p className="text-sm text-white/40">{subtitle}</p>}
    </GlassCard>
  );
}

interface KPIGridProps {
  kpis: {
    title: string;
    value: string;
    subtitle?: string;
  }[];
}

export function KPIGrid({ kpis }: KPIGridProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      {kpis.map((kpi, index) => (
        <KPICard key={index} {...kpi} />
      ))}
    </div>
  );
}
