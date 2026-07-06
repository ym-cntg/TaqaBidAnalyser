"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  GitCompareArrows,
  FileSpreadsheet,
  Zap,
} from "lucide-react";

const navItems = [
  { href: "/", label: "Bid Comparison", icon: GitCompareArrows },
  { href: "/explorer", label: "BOQ Explorer", icon: FileSpreadsheet },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-sidebar-border bg-sidebar">
      <div className="flex h-full flex-col">
        {/* Logo */}
        <div className="flex items-center gap-3 border-b border-sidebar-border px-6 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-[oklch(0.62_0.15_190)] shadow-sm shadow-primary/30">
            <Zap className="h-5 w-5 text-primary-foreground" fill="currentColor" />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight text-sidebar-foreground">
              TAQA Bid Analyzer
            </h1>
            <p className="text-xs text-muted-foreground">D-111808</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 px-3 py-4">
          {navItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
                }`}
              >
                {isActive && (
                  <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-full bg-primary" />
                )}
                <item.icon
                  className={`h-4 w-4 transition-colors ${
                    isActive ? "text-primary" : "group-hover:text-foreground"
                  }`}
                />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="border-t border-sidebar-border px-6 py-4">
          <div className="mb-2 flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <p className="text-xs font-medium text-muted-foreground">
              Live data connected
            </p>
          </div>
          <p className="text-xs text-muted-foreground">Tender D-111808</p>
          <p className="text-xs text-muted-foreground">
            ADDC Eastern Region Substations
          </p>
        </div>
      </div>
    </aside>
  );
}
