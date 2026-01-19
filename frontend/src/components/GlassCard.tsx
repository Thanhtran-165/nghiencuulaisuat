import { cn } from "@/lib/utils";

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
}

export function GlassCard({ children, className }: GlassCardProps) {
  return (
    <div className={cn("glass-card rounded-2xl p-6", className)}>
      {children}
    </div>
  );
}
