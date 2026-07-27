"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckCircle2, ArrowRight } from "lucide-react";
import {
  getWorkflowStatus,
  closeProcurement,
  getReportStatus,
  generateReport,
  type WorkflowStatus,
} from "@/lib/api";
import { useCurrentProject } from "@/lib/project-context";
import { AnalysisNotAvailable } from "@/components/analysis-not-available";

export default function CloseoutPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { project, loading: projectLoading } = useCurrentProject();
  const [status, setStatus] = useState<WorkflowStatus | null>(null);
  const [primaryAward, setPrimaryAward] = useState("");
  const [shortlist, setShortlist] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prefilledFromReport, setPrefilledFromReport] = useState(false);

  useEffect(() => {
    if (!project?.analysis_ready) return;
    setError(null);
    getWorkflowStatus(projectId).then(setStatus);

    getReportStatus().then((s) => {
      if (s.cached) {
        generateReport(false).then((r) => {
          setPrimaryAward(r.report.recommendation.primary_award ?? "");
          setShortlist(r.report.recommendation.shortlist.join(", "));
          setReasoning(r.report.recommendation.reasoning ?? "");
          setPrefilledFromReport(true);
        });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, project?.analysis_ready]);

  async function handleClose() {
    setBusy(true);
    setError(null);
    try {
      const res = await closeProcurement(projectId, {
        primary_award: primaryAward || null,
        shortlist: shortlist.split(",").map((s) => s.trim()).filter(Boolean),
        reasoning,
        notes,
      });
      setStatus((prev) => (prev ? { ...prev, stage: res.stage, closed_at: res.closed_at, award_decision: res.award_decision } : prev));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to close procurement");
    } finally {
      setBusy(false);
    }
  }

  const stage = status?.stage;
  const canClose = stage === "issued";
  const isClosed = stage === "closed";

  if (projectLoading) return null;
  if (!project?.analysis_ready) return <AnalysisNotAvailable project={project} />;

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Close-out &amp; Historical Record</h1>
        <p className="text-muted-foreground mt-1">
          Mark the procurement finished and store the award decision as an auditable record
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-400/40 bg-red-500/5 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {!status ? null : isClosed ? (
        <Card className="border-emerald-500/40 bg-emerald-500/[0.06]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
              Procurement closed
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="text-muted-foreground">
              Closed {status.closed_at ? new Date(status.closed_at).toLocaleString() : ""}
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Primary award</p>
                <p className="font-medium mt-0.5">{status.award_decision?.primary_award || "—"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Shortlist</p>
                <p className="mt-0.5">
                  {status.award_decision?.shortlist.length
                    ? status.award_decision.shortlist.map((b) => (
                        <Badge key={b} variant="secondary" className="mr-1">
                          {b}
                        </Badge>
                      ))
                    : "—"}
                </p>
              </div>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Reasoning</p>
              <p className="mt-0.5">{status.award_decision?.reasoning || "—"}</p>
            </div>
            {status.award_decision?.notes && (
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Closure notes</p>
                <p className="mt-0.5">{status.award_decision.notes}</p>
              </div>
            )}
            <div className="rounded-lg border border-border/60 bg-background/60 px-3 py-2 text-xs text-muted-foreground">
              Maximo reference {status.maximo_reference} · locked by {status.locked_by} · issued{" "}
              {status.issued_at ? new Date(status.issued_at).toLocaleDateString() : ""}
            </div>
          </CardContent>
        </Card>
      ) : canClose ? (
        <Card>
          <CardHeader>
            <CardTitle>Record the award decision</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {prefilledFromReport && (
              <p className="text-xs text-muted-foreground bg-primary/[0.06] rounded-lg px-3 py-2">
                Prefilled from the cached AI recommendation report — adjust before closing if needed.
              </p>
            )}
            <div>
              <label className="text-xs text-muted-foreground uppercase tracking-wide">Primary award</label>
              <input
                type="text"
                value={primaryAward}
                onChange={(e) => setPrimaryAward(e.target.value)}
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                placeholder="Bidder name"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground uppercase tracking-wide">Shortlist (comma-separated)</label>
              <input
                type="text"
                value={shortlist}
                onChange={(e) => setShortlist(e.target.value)}
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground uppercase tracking-wide">Reasoning</label>
              <textarea
                value={reasoning}
                onChange={(e) => setReasoning(e.target.value)}
                rows={3}
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground uppercase tracking-wide">Closure notes</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                placeholder="Anything for the audit trail — retention, follow-ups, etc."
              />
            </div>
            <Button disabled={busy || !primaryAward.trim()} onClick={handleClose}>
              Close procurement{busy ? "…" : ""}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-4 space-y-3">
            <p className="text-sm text-muted-foreground">
              This project isn't ready to close yet — the BOQ template must be issued to market
              first (current stage: <span className="font-medium text-foreground">{stage?.replace(/_/g, " ")}</span>).
            </p>
            <Link
              href={`/projects/${projectId}/template`}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
            >
              Go to BOQ Template Builder <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
