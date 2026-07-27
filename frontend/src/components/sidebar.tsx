"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowLeft,
  ClipboardList,
  FileSpreadsheet,
  FolderInput,
  GitCompareArrows,
  LayoutDashboard,
  Lock,
  ShieldCheck,
  Sparkles,
  TrendingUpDown,
  Zap,
} from "lucide-react";
import { useCurrentProject } from "@/lib/project-context";

interface NavItem {
  slug: string;
  label: string;
  icon: typeof ClipboardList;
  requiresAnalysis: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const SECTIONS: NavSection[] = [
  {
    title: "1. Template Builder",
    items: [{ slug: "template", label: "Template Builder", icon: ClipboardList, requiresAnalysis: true }],
  },
  {
    title: "2. Bid Finalisation",
    items: [
      { slug: "documents", label: "Select Documents", icon: FolderInput, requiresAnalysis: false },
      { slug: "explorer", label: "BOQ Explorer", icon: FileSpreadsheet, requiresAnalysis: true },
    ],
  },
  {
    title: "3. Bid Analysis",
    items: [
      { slug: "compare", label: "Bid Comparison", icon: GitCompareArrows, requiresAnalysis: true },
      { slug: "insights", label: "Insights Dashboard", icon: LayoutDashboard, requiresAnalysis: true },
      { slug: "rounds", label: "Round Tracking", icon: TrendingUpDown, requiresAnalysis: true },
      { slug: "report", label: "Recommendation Report", icon: Sparkles, requiresAnalysis: true },
    ],
  },
  {
    title: "4. Close-out",
    items: [{ slug: "closeout", label: "Close-out", icon: ShieldCheck, requiresAnalysis: true }],
  },
];

export function Sidebar({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const { project } = useCurrentProject();
  const base = `/projects/${projectId}`;

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-sidebar-border bg-sidebar">
      <div className="flex h-full flex-col">
        {/* Logo + project */}
        <div className="border-b border-sidebar-border px-6 py-5">
          <Link href="/projects" className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground mb-3">
            <ArrowLeft className="h-3 w-3" /> All projects
          </Link>
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-[oklch(0.62_0.15_190)] shadow-sm shadow-primary/30 shrink-0">
              <Zap className="h-5 w-5 text-primary-foreground" fill="currentColor" />
            </div>
            <div className="min-w-0">
              <h1
                className="text-sm font-semibold tracking-tight text-sidebar-foreground truncate"
                title={project?.name}
              >
                {project?.name ?? "Loading…"}
              </h1>
              <p className="text-xs text-muted-foreground">{project?.tender_no}</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
          {SECTIONS.map((section) => (
            <div key={section.title}>
              <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {section.title}
              </p>
              <div className="space-y-1">
                {section.items.map((item) => {
                  const href = `${base}/${item.slug}`;
                  const isActive = pathname.startsWith(href);
                  const locked = item.requiresAnalysis && project ? !project.analysis_ready : false;

                  if (locked) {
                    return (
                      <div
                        key={item.slug}
                        title="Not available — this project's BOQ format isn't wired up for analysis yet"
                        className="group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground/40 cursor-not-allowed"
                      >
                        <item.icon className="h-4 w-4" />
                        {item.label}
                        <Lock className="h-3 w-3 ml-auto" />
                      </div>
                    );
                  }

                  return (
                    <Link
                      key={item.slug}
                      href={href}
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
              </div>
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-sidebar-border px-6 py-4">
          <div className="mb-2 flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <p className="text-xs font-medium text-muted-foreground">Live data connected</p>
          </div>
          <p className="text-xs text-muted-foreground truncate">{project?.tender_no}</p>
        </div>
      </div>
    </aside>
  );
}
