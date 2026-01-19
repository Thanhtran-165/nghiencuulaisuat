"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const tabs = [
  { href: "/", label: "Hôm nay" },
  { href: "/lich-su", label: "Lịch sử" },
  { href: "/so-sanh", label: "So sánh" },
  { href: "/may-tinh", label: "Máy tính" },
];

export function TopTabs() {
  const pathname = usePathname();

  return (
    <div data-top-tabs className="border-b border-white/10 mb-8">
      <nav className="flex space-x-1 px-4">
        {tabs.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "glass-button px-6 py-3 rounded-t-lg text-sm font-medium transition-all relative",
              pathname === tab.href
                ? "active text-white"
                : "text-white/60 hover:text-white"
            )}
          >
            {tab.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
