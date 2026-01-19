import { GlassCard } from './GlassCard';

export function ChartSkeleton({ height = 400 }: { height?: number }) {
  return (
    <GlassCard>
      <div className="animate-pulse">
        <div className="h-6 bg-white/10 rounded w-48 mb-4"></div>
        <div
          className="bg-white/5 rounded"
          style={{ height: `${height}px` }}
        ></div>
      </div>
    </GlassCard>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <GlassCard>
      <div className="animate-pulse">
        <div className="h-6 bg-white/10 rounded w-36 mb-4"></div>
        <div className="space-y-3">
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="flex items-center space-x-4">
              <div className="flex-1 h-4 bg-white/5 rounded"></div>
              <div className="w-20 h-4 bg-white/5 rounded"></div>
              <div className="w-24 h-4 bg-white/5 rounded"></div>
            </div>
          ))}
        </div>
      </div>
    </GlassCard>
  );
}

export function BarChartSkeleton({ height = 320 }: { height?: number }) {
  return (
    <GlassCard>
      <div className="animate-pulse">
        <div className="h-6 bg-white/10 rounded w-36 mb-4"></div>
        <div
          className="bg-white/5 rounded flex items-end justify-center p-8"
          style={{ height: `${height}px` }}
        >
          <div className="w-full h-full flex items-end justify-around space-x-2">
            {Array.from({ length: 10 }).map((_, i) => (
              <div
                key={i}
                className="bg-white/10 rounded-t w-full"
                style={{ height: `${30 + Math.random() * 70}%` }}
              ></div>
            ))}
          </div>
        </div>
      </div>
    </GlassCard>
  );
}
