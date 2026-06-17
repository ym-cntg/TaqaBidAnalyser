"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Upload,
  GitCompareArrows,
  AlertTriangle,
  FileSpreadsheet,
  Zap,
} from "lucide-react";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/upload", label: "Upload & Extract", icon: Upload },
  { href: "/compare", label: "Compare Bidders", icon: GitCompareArrows },
  { href: "/flags", label: "Flags & Insights", icon: AlertTriangle },
  { href: "/explorer", label: "BOQ Explorer", icon: FileSpreadsheet },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-border bg-card">
      <div className="flex h-full flex-col">
        {/* Logo */}
        <div className="flex items-center gap-3 border-b border-border px-6 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary">
            <Zap className="h-5 w-5 text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight">
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
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="border-t border-border px-6 py-4">
          <p className="text-xs text-muted-foreground">
            Tender D-111808
          </p>
          <p className="text-xs text-muted-foreground">
            ADDC Eastern Region Substations
          </p>
        </div>
      </div>
    </aside>
  );
}
