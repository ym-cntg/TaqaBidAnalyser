"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
import { getRoundTrend, type RoundTrendResponse } from "@/lib/api";
import { useCurrentProject } from "@/lib/project-context";
import { AnalysisNotAvailable } from "@/components/analysis-not-available";

function formatNum(val: number | null | undefined): string {
  if (val == null) return "—";
  return new Intl.NumberFormat("en-AE", { maximumFractionDigits: 0 }).format(val);
}

const ROUND_LABELS: Record<string, string> = {
  original: "Original",
  round1: "Round 1",
  round2: "Round 2",
  round3: "Round 3",
};

const PALETTE = [
  "#059669", "#2563eb", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#65a30d", "#db2777",
];

export default function RoundsPage() {
  const { project, loading: projectLoading } = useCurrentProject();
  const [data, setData] = useState<RoundTrendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState<string>("all");

  useEffect(() => {
    if (!project?.analysis_ready) return;
    getRoundTrend()
      .then(setData)
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.analysis_ready]);

  const chartData = useMemo(() => {
    if (!data) return [];
    return data.rounds_present.map((round, i) => {
      const row: Record<string, string | number | null> = { round: ROUND_LABELS[round] ?? round };
      for (const bidder of data.bidders) {
        row[bidder.bidder] = bidder.points[i]?.total_contract_price ?? null;
      }
      return row;
    });
  }, [data]);

  const movementFlags = useMemo(() => {
    if (!data) return [];
    return data.flags.filter((f) => severityFilter === "all" || f.severity === severityFilter);
  }, [data, severityFilter]);

  if (projectLoading) return null;
  if (!project?.analysis_ready) return <AnalysisNotAvailable project={project} />;
  if (loading) {
    return <div className="p-8 text-center text-muted-foreground animate-pulse">Loading round trends...</div>;
  }
  if (!data || data.bidders.length === 0) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold tracking-tight">Round-over-Round Tracking</h1>
        <p className="text-muted-foreground mt-4">No multi-round data available.</p>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Round-over-Round Tracking</h1>
        <p className="text-muted-foreground mt-1">
          How each bidder's pricing moved across negotiation rounds ({data.rounds_present.map((r) => ROUND_LABELS[r] ?? r).join(" → ")})
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Contract total by round</CardTitle>
        </CardHeader>
        <CardContent>
          <div style={{ width: "100%", height: 380 }}>
            <ResponsiveContainer>
              <LineChart data={chartData} margin={{ left: 8, right: 24 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="round" fontSize={12} />
                <YAxis tickFormatter={(v) => formatNum(v)} fontSize={11} width={80} />
                <Tooltip formatter={(v) => `AED ${formatNum(Number(v))}`} />
                <Legend />
                {data.bidders.map((b, i) => (
                  <Line
                    key={b.bidder}
                    type="monotone"
                    dataKey={b.bidder}
                    stroke={PALETTE[i % PALETTE.length]}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Contract totals table</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="text-left py-2 px-2">Bidder</th>
                  {data.rounds_present.map((r) => (
                    <th key={r} className="text-right py-2 px-2">{ROUND_LABELS[r] ?? r}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.bidders.map((b) => (
                  <tr key={b.bidder} className="border-t border-border/60">
                    <td className="py-2 px-2 font-medium">{b.bidder}</td>
                    {b.points.map((p) => (
                      <td key={p.round_name} className="py-2 px-2 text-right font-mono">
                        {formatNum(p.total_contract_price)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between gap-4 flex-wrap">
            Anomalous movement flags
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm font-normal"
            >
              <option value="all">All severities ({data.flags.length})</option>
              <option value="critical">Critical only</option>
              <option value="warning">Warning only</option>
            </select>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-3">
            An item price that rises between rounds, or one bidder discounting an item far more
            steeply than peers did on that same item, both surface here — negotiation rounds
            should only move pricing down evenly.
          </p>
          <div className="overflow-x-auto rounded-lg border border-border/60 max-h-[420px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted/90 backdrop-blur">
                <tr className="border-b border-border/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="text-left py-2 px-2">Severity</th>
                  <th className="text-left py-2 px-2">Bidder</th>
                  <th className="text-left py-2 px-2">Lot</th>
                  <th className="text-left py-2 px-2">Item</th>
                  <th className="text-left py-2 px-2">Detail</th>
                </tr>
              </thead>
              <tbody>
                {movementFlags.slice(0, 300).map((f, i) => (
                  <tr key={i} className="border-t border-border/60 odd:bg-muted/[0.15]">
                    <td className="py-1.5 px-2">
                      <Badge className={f.severity === "critical" ? "bg-red-600 text-white" : "bg-amber-500 text-white"}>
                        {f.severity}
                      </Badge>
                    </td>
                    <td className="py-1.5 px-2">{f.bidder}</td>
                    <td className="py-1.5 px-2 text-xs">{f.lot}</td>
                    <td className="py-1.5 px-2 font-mono text-xs">{f.item_no}</td>
                    <td className="py-1.5 px-2 text-xs text-muted-foreground max-w-[500px]">{f.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {movementFlags.length > 300 && (
            <p className="text-xs text-muted-foreground mt-2">
              Showing 300 of {movementFlags.length} — narrow the severity filter to see more.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
