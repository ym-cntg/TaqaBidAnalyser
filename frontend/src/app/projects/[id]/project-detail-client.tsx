"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { ApiError, getProject, type ProjectSummary } from "@/lib/api";
import { BOQ_CATEGORY_BADGE_VARIANT, BOQ_CATEGORY_LABELS } from "@/lib/boq-category";
import { formatDate } from "@/lib/format";
import { NegotiationReport } from "./negotiation-report";
import { RfqComparison } from "./rfq-comparison";
import { RoundTracking } from "./round-tracking";

export function ProjectDetailClient({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error" | "not-found">("loading");
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"comparison" | "rounds" | "report">("comparison");

  useEffect(() => {
    getProject(projectId)
      .then((p) => {
        setProject(p);
        setStatus("ok");
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setStatus("not-found");
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
  }, [projectId]);

  return (
    <main className="min-h-screen bg-app-gradient">
      <div className="mx-auto max-w-[1600px] px-6 py-6 space-y-4">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← Projects
        </Link>

        {status === "loading" && (
          <p className="text-center py-12 text-muted-foreground animate-pulse">Loading…</p>
        )}

        {status === "not-found" && (
          <p className="text-center py-12 text-muted-foreground">Unknown project.</p>
        )}

        {status === "error" && (
          <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-600">
            {error}
          </div>
        )}

        {status === "ok" && project && (
          <>
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h1 className="text-2xl font-bold tracking-tight">{project.name}</h1>
                <p className="text-muted-foreground mt-1">
                  <span className="font-mono text-sm">{project.rfqnum}</span> —{" "}
                  {project.rfq_description ?? "—"}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Created by {project.user_display_name ?? "unknown"} on {formatDate(project.created_at)}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {project.rfq_status && <Badge variant="outline">{project.rfq_status}</Badge>}
                {project.org_id && <Badge variant="outline">{project.org_id}</Badge>}
                {project.boq_category && (
                  <Badge variant={BOQ_CATEGORY_BADGE_VARIANT[project.boq_category]}>
                    {BOQ_CATEGORY_LABELS[project.boq_category]}
                  </Badge>
                )}
              </div>
            </div>

            <div className="inline-flex gap-1 rounded-lg bg-muted p-1">
              <button
                onClick={() => setActiveTab("comparison")}
                className={`rounded-md px-4 py-1.5 text-sm font-medium transition-all ${
                  activeTab === "comparison"
                    ? "bg-card text-primary shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                BOQ Comparison
              </button>
              <button
                onClick={() => setActiveTab("rounds")}
                className={`rounded-md px-4 py-1.5 text-sm font-medium transition-all ${
                  activeTab === "rounds"
                    ? "bg-card text-primary shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Round Tracking
              </button>
              <button
                onClick={() => setActiveTab("report")}
                className={`rounded-md px-4 py-1.5 text-sm font-medium transition-all ${
                  activeTab === "report"
                    ? "bg-card text-primary shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Negotiation Report
              </button>
            </div>

            {activeTab === "comparison" && <RfqComparison rfqnum={project.rfqnum} />}
            {activeTab === "rounds" && <RoundTracking rfqnum={project.rfqnum} />}
            {activeTab === "report" && <NegotiationReport rfqnum={project.rfqnum} />}
          </>
        )}
      </div>
    </main>
  );
}
