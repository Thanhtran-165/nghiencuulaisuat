"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

function join(basePath: string, href: string) {
  if (!basePath) return href;
  const base = basePath.endsWith("/") ? basePath.slice(0, -1) : basePath;
  if (href === "/") return base || "/";
  return `${base}${href}`;
}

export function TopTabs({ basePath = "" }: { basePath?: string }) {
  const pathname = usePathname();
  const tabs = [
    { href: join(basePath, "/"), label: "Hôm nay" },
    { href: join(basePath, "/lich-su"), label: "Lịch sử" },
    { href: join(basePath, "/so-sanh"), label: "So sánh" },
    { href: join(basePath, "/may-tinh"), label: "Máy tính" },
    { href: join(basePath, "/nghien-cuu"), label: "Nghiên cứu" },
  ];

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
