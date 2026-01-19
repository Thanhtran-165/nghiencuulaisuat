"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";

type MenuItem = { href: string; label: string };

function useOutsideClick(ref: React.RefObject<HTMLElement>, onOutside: () => void) {
  useEffect(() => {
    function handler(event: MouseEvent) {
      const el = ref.current;
      if (!el) return;
      if (event.target instanceof Node && el.contains(event.target)) return;
      onOutside();
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [ref, onOutside]);
}

export function NavBar() {
  const pathname = usePathname();
  const containerRef = useRef<HTMLDivElement>(null);

  const [marketOpen, setMarketOpen] = useState(false);
  const [researchOpen, setResearchOpen] = useState(false);

  const marketItems: MenuItem[] = useMemo(
    () => [
      { href: "/yield-curve", label: "Yield Curve" },
      { href: "/interbank", label: "Interbank" },
      { href: "/auctions", label: "Auctions" },
      { href: "/secondary", label: "Secondary" },
      { href: "/policy", label: "Policy" },
      { href: "/snapshot/today", label: "Snapshot" },
    ],
    []
  );

  const researchItems: MenuItem[] = useMemo(
    () => [
      { href: "/transmission", label: "Transmission" },
      { href: "/causality", label: "Causality" },
      { href: "/stress", label: "Stress" },
      { href: "/data", label: "Data" },
    ],
    []
  );

  function closeAll() {
    setMarketOpen(false);
    setResearchOpen(false);
  }

  useEffect(() => {
    closeAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") closeAll();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useOutsideClick(containerRef, () => closeAll());

  return (
    <div ref={containerRef} className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap justify-end">
        <Link
          className="glass-button px-4 py-2 rounded-lg text-sm text-white/80 hover:text-white"
          href="/"
          onClick={() => closeAll()}
        >
          Dashboard
        </Link>
        <Link
          className="glass-button px-4 py-2 rounded-lg text-sm text-white/80 hover:text-white"
          href="/nhan-dinh"
          onClick={() => closeAll()}
        >
          Nhận định
        </Link>
        <Link
          className="glass-button px-4 py-2 rounded-lg text-sm text-white/80 hover:text-white"
          href="/lai-suat"
          onClick={() => closeAll()}
        >
          Lãi suất
        </Link>

        <button
          type="button"
          className="glass-button px-4 py-2 rounded-lg text-sm text-white/80 hover:text-white"
          aria-expanded={marketOpen}
          onClick={() => {
            setMarketOpen((v) => !v);
            setResearchOpen(false);
          }}
        >
          Thị trường
        </button>

        <button
          type="button"
          className="glass-button px-4 py-2 rounded-lg text-sm text-white/80 hover:text-white"
          aria-expanded={researchOpen}
          onClick={() => {
            setResearchOpen((v) => !v);
            setMarketOpen(false);
          }}
        >
          Nghiên cứu
        </button>

        <Link
          className="glass-button px-4 py-2 rounded-lg text-sm text-white/80 hover:text-white"
          href="/admin"
          onClick={() => closeAll()}
        >
          Admin
        </Link>
      </div>

      {marketOpen ? (
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {marketItems.map((item) => (
            <Link
              key={item.href}
              className="glass-button px-4 py-2 rounded-lg text-sm text-white/80 hover:text-white"
              href={item.href}
              onClick={() => closeAll()}
            >
              {item.label}
            </Link>
          ))}
        </div>
      ) : null}

      {researchOpen ? (
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {researchItems.map((item) => (
            <Link
              key={item.href}
              className="glass-button px-4 py-2 rounded-lg text-sm text-white/80 hover:text-white"
              href={item.href}
              onClick={() => closeAll()}
            >
              {item.label}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
