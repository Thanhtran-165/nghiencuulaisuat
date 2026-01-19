import Link from "next/link";
import { GlassCard } from "@/components/GlassCard";

export default function LabPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white">Lab hub</h1>
        <p className="text-white/60 mt-2">Khu vực nghiên cứu (đầy đủ) — tất cả chạy trên Next.js.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Transmission</div>
          <div className="text-white font-semibold mb-2">Bond Transmission Analytics</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/transmission">
            Mở Transmission →
          </Link>
        </GlassCard>
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Causality</div>
          <div className="text-white font-semibold mb-2">Ai dẫn ai? (dẫn dắt & độ trễ)</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/causality">
            Mở Causality →
          </Link>
        </GlassCard>
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Stress</div>
          <div className="text-white font-semibold mb-2">BondY Stress Index</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/stress">
            Mở Stress →
          </Link>
        </GlassCard>
        <GlassCard>
          <div className="text-white/60 text-sm mb-2">Data</div>
          <div className="text-white font-semibold mb-2">Catalog & schema</div>
          <Link className="text-white/90 hover:text-white underline text-sm" href="/data">
            Mở Data →
          </Link>
        </GlassCard>
      </div>

      <GlassCard>
        <div className="text-white/60 text-sm mb-2">Gợi ý</div>
        <div className="text-white/70 text-sm">
          Nếu bạn cần “kết luận dễ hiểu”, dùng tab <Link className="underline hover:text-white" href="/nhan-dinh">Nhận định</Link>. Lab hub chủ yếu dành cho kiểm chứng học thuật.
        </div>
      </GlassCard>
    </div>
  );
}

