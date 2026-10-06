"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import {
  ApiError,
  getProject,
  getUploadProject,
  type ProjectSummary,
  type UploadProject,
} from "@/lib/api";
import { BOQ_CATEGORY_BADGE_VARIANT, BOQ_CATEGORY_LABELS } from "@/lib/boq-category";
import { formatDate } from "@/lib/format";
import { BetaBadge, BetaNotice } from "@/app/uploads/[id]/beta-notice";
import { NegotiationReport } from "./negotiation-report";
import { RfqComparison } from "./rfq-comparison";
import { RoundTracking } from "./round-tracking";

export function ProjectDetailClient({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<ProjectSummary | null>(null);
  // An uploaded project is not in bid_analyzer_projects, so getProject
  // 404s for it. That 404 is the signal to look in the upload store,
  // not an error.
  const [upload, setUpload] = useState<UploadProject | null>(null);
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
        // Any failure here is a reason to look in the upload store, not
        // just a 404. An uploaded project is never a row in
        // bid_analyzer_projects, and that table is grant-blocked, so
        // the lookup returns 503 rather than 404 in exactly the
        // environment uploads are most useful in. Only if the upload
        // store misses too is the original error the real one.
        getUploadProject(projectId)
          .then((u) => {
            setUpload(u);
            setStatus("ok");
          })
          .catch(() => {
            if (err instanceof ApiError && err.status === 404) {
              setStatus("not-found");
              return;
            }
            setError(err instanceof Error ? err.message : String(err));
            setStatus("error");
          });
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

        {status === "ok" && upload && (
          <>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h1 className="flex items-center gap-2 text-xl font-semibold">
                  {upload.name} <BetaBadge />
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Uploaded Excel · {upload.vendors.length} vendor
                  {upload.vendors.length === 1 ? "" : "s"} · {upload.rounds.length} round
                  {upload.rounds.length === 1 ? "" : "s"} · {upload.line_count} lines
                </p>
              </div>
              <Link
                href={`/uploads/${upload.project_id}`}
                className="text-sm text-primary underline-offset-4 hover:underline"
              >
                Review or edit the uploaded BOQ
              </Link>
            </div>

            <BetaNotice compact />

            {/* The analysis endpoints take the project id wherever an
                rfqnum would go, so these three tabs are the same
                components the Maximo path uses, unchanged. */}
            <div className="inline-flex gap-1 rounded-lg bg-muted p-1">
              {([
                ["comparison", "BOQ Comparison"],
                ["rounds", "Round Tracking"],
                ["report", "Negotiation Report"],
              ] as const).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={`rounded-md px-4 py-1.5 text-sm font-medium transition-all ${
                    activeTab === key
                      ? "bg-card text-primary shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {activeTab === "comparison" && <RfqComparison rfqnum={upload.project_id} />}
            {activeTab === "rounds" && <RoundTracking rfqnum={upload.project_id} />}
            {activeTab === "report" && <NegotiationReport rfqnum={upload.project_id} />}
          </>
        )}
      </div>
    </main>
  );
}
