"use client";

import { Download, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  generateNegotiationNarrative,
  getNegotiationReport,
  negotiationReportExportUrl,
  NarrativeUnavailableError,
  type NarrativeReport,
  type NegotiationReportResponse,
  type TopIssue,
} from "@/lib/api";
import { formatAED } from "@/lib/format";

function vendorLabel(vendor: string, name: string | null): string {
  return name ?? vendor;
}

function issueLabel(issue: TopIssue): string {
  const source = issue.source === "round" ? "Round" : "BOQ";
  return `${source} · ${issue.severity}`;
}

type NarrativeState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; report: NarrativeReport }
  | { status: "not-configured"; message: string }
  | { status: "error"; message: string };

function vendorLabelFrom(data: NegotiationReportResponse, vendor: string): string {
  return data.vendors.find((v) => v.vendor === vendor)?.name ?? vendor;
}

function AiSummaryCard({ rfqnum, data }: { rfqnum: string; data: NegotiationReportResponse }) {
  const [state, setState] = useState<NarrativeState>({ status: "idle" });

  function generate() {
    setState({ status: "loading" });
    generateNegotiationNarrative(rfqnum)
      .then((report) => setState({ status: "ok", report }))
      .catch((err) => {
        if (err instanceof NarrativeUnavailableError && err.notConfigured) {
          setState({ status: "not-configured", message: err.message });
        } else {
          setState({ status: "error", message: err instanceof Error ? err.message : String(err) });
        }
      });
  }

  return (
    <div className="rounded-xl border border-border/60 shadow-sm p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <span className="font-semibold text-sm">AI summary</span>
        </div>
        {state.status === "ok" && (
          <Button variant="outline" size="sm" onClick={generate}>
            Regenerate
          </Button>
        )}
      </div>

      {state.status === "idle" && (
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-muted-foreground">
            Generate an AI-written overview and per-vendor notes from the ranked data above.
            Advisory only — it never makes an award decision, and can only reference vendors and
            numbers already in this report.
          </p>
          <Button size="sm" onClick={generate}>
            <Sparkles className="h-4 w-4" /> Generate AI summary
          </Button>
        </div>
      )}

      {state.status === "loading" && (
        <p className="text-sm text-muted-foreground animate-pulse py-4">Generating…</p>
      )}

      {state.status === "not-configured" && (
        <div className="rounded-lg border border-amber-400/40 bg-amber-500/5 p-3 text-sm">
          <p className="font-medium">AI summary isn&apos;t set up yet</p>
          <p className="text-muted-foreground mt-1 text-xs">{state.message}</p>
        </div>
      )}

      {state.status === "error" && (
        <div className="space-y-2">
          <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-3 text-sm text-red-600">
            {state.message}
          </div>
          <Button variant="outline" size="sm" onClick={generate}>
            Try again
          </Button>
        </div>
      )}

      {state.status === "ok" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-primary/20 bg-primary/[0.04] px-3 py-2 text-xs text-muted-foreground">
            AI-generated — advisory only, not a decision. Every vendor/number below comes from the
            ranked data above; anything it couldn&apos;t verify was removed automatically.
          </div>
          <p className="text-sm leading-relaxed">{state.report.executive_summary}</p>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {state.report.observations.map((obs) => (
              <div key={obs.vendor} className="rounded-lg border border-border/60 p-3 space-y-1.5">
                <div className="font-medium text-sm">{vendorLabelFrom(data, obs.vendor)}</div>
                <p className="text-sm text-muted-foreground">{obs.note}</p>
                {obs.talking_points.length > 0 && (
                  <ul className="list-disc list-inside text-xs text-muted-foreground space-y-0.5">
                    {obs.talking_points.map((p, i) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>

          {state.report.caveats.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Caveats</p>
              <ul className="list-disc list-inside text-xs text-muted-foreground space-y-0.5">
                {state.report.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function NegotiationReport({ rfqnum }: { rfqnum: string }) {
  const [data, setData] = useState<NegotiationReportResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setStatus("loading");
    setError(null);
    getNegotiationReport(rfqnum)
      .then((res) => {
        setData(res);
        setStatus("ok");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
  }, [rfqnum]);

  if (status === "loading") {
    return <div className="text-center py-12 text-muted-foreground animate-pulse">Loading report…</div>;
  }
  if (status === "error") {
    return (
      <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-600">{error}</div>
    );
  }
  if (!data || data.vendors.length === 0) {
    return <div className="text-center py-12 text-muted-foreground">No vendor pricing found for this RFQ yet.</div>;
  }

  return (
    <div className="space-y-6">
      <AiSummaryCard rfqnum={rfqnum} data={data} />

      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">
          Ranked by contract total, lowest first. Not a recommendation — the numbers and flags
          below are for the analyst to weigh.
          {!data.has_round_data && " No negotiation-round history for this RFQ yet, so round flags are all zero."}
        </p>
        <a href={negotiationReportExportUrl(rfqnum)}>
          <Button variant="outline" size="sm">
            <Download className="h-4 w-4" /> Download Excel
          </Button>
        </a>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {data.vendors.map((v) => (
          <div key={v.vendor} className="rounded-xl border border-border/60 shadow-sm p-4 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{vendorLabel(v.vendor, v.name)}</span>
                  {v.rank === 1 ? (
                    <Badge className="bg-emerald-600 text-white text-[10px]">Lowest</Badge>
                  ) : (
                    <Badge variant="outline" className="text-[10px]">
                      #{v.rank} · +{v.pct_above_lowest.toFixed(1)}% vs lowest
                    </Badge>
                  )}
                </div>
                <div className="font-mono text-xs text-muted-foreground">{v.vendor}</div>
              </div>
              <div className="text-right font-mono text-sm font-semibold">{formatAED(v.contract_total)}</div>
            </div>

            <div className="flex flex-wrap gap-1">
              {v.round_critical_count > 0 && (
                <Badge className="bg-red-600 text-white">{v.round_critical_count} price increase{v.round_critical_count > 1 ? "s" : ""}</Badge>
              )}
              {v.round_warning_count > 0 && (
                <Badge className="bg-amber-500 text-white">{v.round_warning_count} steep discount{v.round_warning_count > 1 ? "s" : ""}</Badge>
              )}
              {v.arithmetic_error_count > 0 && (
                <Badge variant="destructive">{v.arithmetic_error_count} arithmetic error{v.arithmetic_error_count > 1 ? "s" : ""}</Badge>
              )}
              {v.unquoted_count > 0 && <Badge variant="outline">{v.unquoted_count} unquoted</Badge>}
              {v.outlier_count > 0 && <Badge variant="secondary">{v.outlier_count} outlier{v.outlier_count > 1 ? "s" : ""}</Badge>}
              {v.zero_price_count > 0 && <Badge variant="outline">{v.zero_price_count} zero-priced</Badge>}
              {v.round_critical_count === 0 &&
                v.round_warning_count === 0 &&
                v.arithmetic_error_count === 0 &&
                v.unquoted_count === 0 &&
                v.outlier_count === 0 &&
                v.zero_price_count === 0 && <span className="text-xs text-muted-foreground">No flags</span>}
            </div>

            {v.top_issues.length > 0 && (
              <ul className="space-y-1.5 text-sm">
                {v.top_issues.map((issue, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span
                      className={`mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                        issue.severity === "critical" ? "bg-red-500" : "bg-amber-500"
                      }`}
                    />
                    <span className="text-muted-foreground">
                      <span className="font-mono text-xs text-foreground">Line {issue.rfqlinenum}</span>{" "}
                      <span className="text-xs">({issueLabel(issue)})</span> — {issue.detail}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>

      {data.not_submitted.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Invited but did not submit any pricing:{" "}
          {data.not_submitted.map((v) => vendorLabel(v.vendor, v.name)).join(", ")}
        </p>
      )}
    </div>
  );
}
