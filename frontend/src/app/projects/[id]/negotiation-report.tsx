"use client";

import { Download } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  getNegotiationReport,
  negotiationReportExportUrl,
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
