"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { getRoundTrend, type RoundTrendResponse } from "@/lib/api";
import { formatAED, formatDate, formatNumber } from "@/lib/format";
import { formatRoundLabel } from "@/lib/rounds";

// dataviz skill's validated reference categorical palette, adopted as
// this app's --chart-1..5 tokens (see globals.css) -- fixed order, never
// cycled. More than 5 series can't be told apart, so anything past the
// 5th vendor is table-only, not a 6th generated hue.
const CHART_COLOR_VARS = ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5"];
const MAX_CHART_LINES = 5;

function vendorLabel(vendor: string, name: string | null): string {
  return name ?? vendor;
}

export function RoundTracking({ rfqnum }: { rfqnum: string }) {
  const [data, setData] = useState<RoundTrendResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<"all" | "critical" | "warning">("all");

  useEffect(() => {
    setStatus("loading");
    setError(null);
    getRoundTrend(rfqnum)
      .then((res) => {
        setData(res);
        setStatus("ok");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
  }, [rfqnum]);

  const chartVendors = useMemo(() => {
    if (!data) return [];
    // Most materially significant vendors (highest final-round total)
    // get the plotted lines; the rest stay table-only below.
    const withFinal = data.vendors.map((v) => ({
      v,
      final: [...v.points].reverse().find((p) => p.contract_total != null)?.contract_total ?? 0,
    }));
    withFinal.sort((a, b) => b.final - a.final);
    return withFinal.map((x) => x.v);
  }, [data]);

  const plottedVendors = chartVendors.slice(0, MAX_CHART_LINES);
  const overflowCount = Math.max(0, chartVendors.length - MAX_CHART_LINES);

  const chartData = useMemo(() => {
    if (!data) return [];
    return data.rounds_present.map((round) => {
      const row: Record<string, string | number | null> = { round: formatRoundLabel(round) };
      for (const vendor of plottedVendors) {
        const point = vendor.points.find((p) => p.round === round);
        row[vendorLabel(vendor.vendor, vendor.name)] = point?.contract_total ?? null;
      }
      return row;
    });
  }, [data, plottedVendors]);

  const visibleFlags = useMemo(() => {
    if (!data) return [];
    return data.flags.filter((f) => severityFilter === "all" || f.severity === severityFilter);
  }, [data, severityFilter]);

  if (status === "loading") {
    return (
      <div className="text-center py-12 text-muted-foreground animate-pulse">Loading round trend…</div>
    );
  }
  if (status === "error") {
    return (
      <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-600">{error}</div>
    );
  }
  if (!data || data.vendors.length === 0 || data.rounds_present.length < 2) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No negotiation-round history found for this RFQ yet.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border/60 shadow-sm p-4">
        <div style={{ width: "100%", height: 360 }}>
          <ResponsiveContainer>
            <LineChart data={chartData} margin={{ left: 8, right: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="round" fontSize={12} stroke="var(--muted-foreground)" />
              <YAxis
                tickFormatter={(v) => formatNumber(v)}
                fontSize={11}
                width={80}
                stroke="var(--muted-foreground)"
              />
              <Tooltip
                formatter={(v) => formatAED(typeof v === "number" ? v : null)}
                contentStyle={{
                  background: "var(--popover)",
                  color: "var(--popover-foreground)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                cursor={{ stroke: "var(--border)" }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {plottedVendors.map((v, i) => (
                <Line
                  key={v.vendor}
                  type="monotone"
                  dataKey={vendorLabel(v.vendor, v.name)}
                  stroke={`var(${CHART_COLOR_VARS[i % CHART_COLOR_VARS.length]})`}
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        {overflowCount > 0 && (
          <p className="mt-2 text-xs text-muted-foreground">
            +{overflowCount} more vendor{overflowCount > 1 ? "s" : ""} — see table below.
          </p>
        )}
      </div>

      {/* Contract totals table -- also the visible-table "relief" the
          chart's sub-3:1-contrast colors require (see globals.css). */}
      <div className="rounded-xl border border-border/60 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/60 border-b border-border/60">
                <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Vendor
                </th>
                {data.rounds_present.map((r) => (
                  <th
                    key={r}
                    className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                  >
                    {formatRoundLabel(r)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.vendors.map((v) => (
                <tr key={v.vendor} className="border-t border-border/60 odd:bg-muted/[0.15]">
                  <td className="px-3 py-2 font-medium">{vendorLabel(v.vendor, v.name)}</td>
                  {v.points.map((p) => (
                    <td
                      key={p.round}
                      className="px-3 py-2 text-right font-mono text-xs"
                      title={p.date ? formatDate(p.date) : undefined}
                    >
                      {p.contract_total != null ? formatAED(p.contract_total) : "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Flags */}
      <div className="rounded-xl border border-border/60 shadow-sm p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-4">
          <h3 className="text-sm font-semibold">Anomalous movement flags</h3>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as "all" | "critical" | "warning")}
            className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
          >
            <option value="all">All severities ({data.flags.length})</option>
            <option value="critical">Critical only</option>
            <option value="warning">Warning only</option>
          </select>
        </div>
        <p className="mb-3 text-sm text-muted-foreground">
          A line price that rises between rounds, or one vendor discounting a line far more steeply
          than peers did on that same line, both surface here — negotiation rounds should only move
          pricing down, evenly.
        </p>
        {visibleFlags.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No flags at this severity.</p>
        ) : (
          <div className="max-h-[420px] overflow-y-auto overflow-x-auto rounded-lg border border-border/60">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted/90 backdrop-blur">
                <tr className="border-b border-border/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-2 py-2 text-left">Severity</th>
                  <th className="px-2 py-2 text-left">Vendor</th>
                  <th className="px-2 py-2 text-left">Line</th>
                  <th className="px-2 py-2 text-left">Detail</th>
                </tr>
              </thead>
              <tbody>
                {visibleFlags.slice(0, 300).map((f, i) => (
                  <tr key={i} className="border-t border-border/60 odd:bg-muted/[0.15]">
                    <td className="px-2 py-1.5">
                      <Badge className={f.severity === "critical" ? "bg-red-600 text-white" : "bg-amber-500 text-white"}>
                        {f.severity}
                      </Badge>
                    </td>
                    <td className="px-2 py-1.5">{vendorLabel(f.vendor, f.name)}</td>
                    <td className="px-2 py-1.5 font-mono text-xs">{f.rfqlinenum}</td>
                    <td className="max-w-[500px] px-2 py-1.5 text-xs text-muted-foreground">
                      {f.description && <span className="text-foreground">{f.description}: </span>}
                      {f.detail}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {visibleFlags.length > 300 && (
          <p className="mt-2 text-xs text-muted-foreground">
            Showing 300 of {visibleFlags.length} — narrow the severity filter to see more.
          </p>
        )}
      </div>
    </div>
  );
}
