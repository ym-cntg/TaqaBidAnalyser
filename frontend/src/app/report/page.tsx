"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sparkles,
  RefreshCw,
  Download,
  AlertTriangle,
  Loader2,
  Settings,
} from "lucide-react";
import {
  getReportStatus,
  generateReport,
  reportExportUrl,
  ReportUnavailableError,
  type ReportStatus,
  type RecommendationReport,
} from "@/lib/api";

type ViewState = "idle" | "generating" | "loaded" | "error" | "not_configured";

const POSITION_LABEL: Record<string, string> = {
  lowest: "Lowest",
  competitive: "Competitive",
  highest: "Highest",
  excluded_data_gap: "Data gap — excluded",
  unknown: "Unknown",
};

function positionBadgeClass(position: string): string {
  switch (position) {
    case "lowest":
      return "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400";
    case "highest":
      return "bg-red-500/15 text-red-600 dark:text-red-400";
    case "excluded_data_gap":
      return "bg-amber-500/15 text-amber-600 dark:text-amber-400";
    default:
      return "bg-muted text-muted-foreground";
  }
}

export default function ReportPage() {
  const [status, setStatus] = useState<ReportStatus | null>(null);
  const [report, setReport] = useState<RecommendationReport | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [view, setView] = useState<ViewState>("idle");
  const [error, setError] = useState<{ reason: string; message: string } | null>(null);

  useEffect(() => {
    getReportStatus().then((s) => {
      setStatus(s);
      if (!s.llm_configured) {
        setView("not_configured");
      } else if (s.cached) {
        // Status alone doesn't include the report body — fetch it via a
        // non-forced generate call, which returns the cache hit for free.
        runGenerate(false);
      }
    });
  }, []);

  async function runGenerate(force: boolean) {
    setView("generating");
    setError(null);
    try {
      const res = await generateReport(force);
      setReport(res.report);
      setGeneratedAt(res.generated_at);
      setView("loaded");
      getReportStatus().then(setStatus);
    } catch (e) {
      if (e instanceof ReportUnavailableError) {
        if (e.reason === "not_configured") {
          setView("not_configured");
        } else {
          setError({ reason: e.reason, message: e.message });
          setView("error");
        }
      } else {
        setError({ reason: "api_error", message: e instanceof Error ? e.message : "Unknown error" });
        setView("error");
      }
    }
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-primary" />
            Recommendation Report
          </h1>
          <p className="text-muted-foreground mt-1">
            LLM-generated award recommendation and per-bidder negotiation notes for
            this round
          </p>
        </div>

        {view === "loaded" && (
          <div className="flex items-center gap-2">
            <a href={reportExportUrl("xlsx")}>
              <Button variant="outline" size="sm">
                <Download className="h-4 w-4" /> Excel
              </Button>
            </a>
            <a href={reportExportUrl("html")}>
              <Button variant="outline" size="sm">
                <Download className="h-4 w-4" /> HTML
              </Button>
            </a>
            <Button size="sm" onClick={() => runGenerate(true)}>
              <RefreshCw className="h-4 w-4" /> Regenerate
            </Button>
          </div>
        )}
      </div>

      {view === "not_configured" && (
        <Card>
          <CardContent className="flex items-start gap-3 py-6">
            <Settings className="h-5 w-5 text-muted-foreground mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">LLM not configured</p>
              <p className="text-sm text-muted-foreground mt-1">
                Set <code className="text-xs bg-muted px-1 py-0.5 rounded">AZURE_OPENAI_API_KEY</code>,{" "}
                <code className="text-xs bg-muted px-1 py-0.5 rounded">AZURE_OPENAI_ENDPOINT</code>,{" "}
                <code className="text-xs bg-muted px-1 py-0.5 rounded">AZURE_OPENAI_API_VERSION</code>, and{" "}
                <code className="text-xs bg-muted px-1 py-0.5 rounded">AZURE_OPENAI_MODEL</code> in the
                backend environment to enable this feature.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {view === "idle" && (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-12">
            <p className="text-muted-foreground text-sm">
              Generate an executive summary, award recommendation, and per-bidder
              negotiation notes from the current bid comparison.
            </p>
            <Button onClick={() => runGenerate(false)}>
              <Sparkles className="h-4 w-4" /> Generate Recommendation Report
            </Button>
          </CardContent>
        </Card>
      )}

      {view === "generating" && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <p className="text-muted-foreground text-sm">
              Generating report — this can take up to 20-30 seconds.
            </p>
          </CardContent>
        </Card>
      )}

      {view === "error" && (
        <Card>
          <CardContent className="flex items-start gap-3 py-6">
            <AlertTriangle className="h-5 w-5 text-destructive mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="font-medium">Report generation failed</p>
              <p className="text-sm text-muted-foreground mt-1">{error?.message}</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => runGenerate(true)}>
              <RefreshCw className="h-4 w-4" /> Try again
            </Button>
          </CardContent>
        </Card>
      )}

      {view === "loaded" && report && (
        <div className="space-y-6">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {generatedAt && <span>Generated {new Date(generatedAt).toLocaleString()}</span>}
            {status?.stale && (
              <Badge className="bg-amber-500/15 text-amber-600 dark:text-amber-400">
                Data has changed since this was generated
              </Badge>
            )}
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Executive Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed">{report.executive_summary}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recommendation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge className="bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                  {report.recommendation.primary_award ?? "No clear recommendation"}
                </Badge>
                {report.recommendation.shortlist
                  .filter((b) => b !== report.recommendation.primary_award)
                  .map((b) => (
                    <Badge key={b} variant="outline">
                      {b}
                    </Badge>
                  ))}
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {report.recommendation.reasoning}
              </p>
            </CardContent>
          </Card>

          {report.caveats.length > 0 && (
            <Card className="border-amber-400/40 bg-amber-500/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
                  <AlertTriangle className="h-4 w-4" /> Caveats
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="text-sm space-y-1.5 list-disc list-inside text-muted-foreground">
                  {report.caveats.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          <div>
            <h2 className="text-lg font-semibold mb-3">Bidder Negotiation Notes</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(report.bidder_notes).map(([bidder, note]) => {
                const isGap = note.position === "excluded_data_gap";
                return (
                  <Card key={bidder} className={isGap ? "opacity-60 border-dashed" : ""}>
                    <CardHeader>
                      <CardTitle className="flex items-center justify-between gap-2 text-base">
                        {bidder}
                        <Badge className={positionBadgeClass(note.position)}>
                          {POSITION_LABEL[note.position] ?? note.position}
                        </Badge>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <p className="text-sm">{note.summary}</p>
                      {note.negotiation_points.length > 0 && (
                        <ul className="text-sm space-y-1 list-disc list-inside text-muted-foreground">
                          {note.negotiation_points.map((p, i) => (
                            <li key={i}>{p}</li>
                          ))}
                        </ul>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
