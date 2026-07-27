"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getInsights, comparisonExportUrl, type InsightsResponse, type Flag } from "@/lib/api";
import { Download } from "lucide-react";
import { useCurrentProject } from "@/lib/project-context";
import { AnalysisNotAvailable } from "@/components/analysis-not-available";

function formatNum(val: number | null | undefined): string {
  if (val == null) return "—";
  return new Intl.NumberFormat("en-AE", { maximumFractionDigits: 0 }).format(val);
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: "#dc2626",
  warning: "#d97706",
  info: "#2563eb",
};

const BAR_LOWEST = "#059669";
const BAR_NORMAL = "#64748b";
const BAR_GAP = "#cbd5e1";

const CATEGORY_LABELS: Record<string, string> = {
  unquoted: "Unquoted item",
  arithmetic: "Arithmetic error",
  unbalanced: "Unbalanced bidding",
  outlier: "Price outlier",
  missing: "Missing bid data",
  cross_lot: "Cross-lot inconsistency",
  tampering: "Description tampering",
  round_movement: "Round movement",
};

export default function InsightsPage() {
  const { project, loading: projectLoading } = useCurrentProject();
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [bidderFilter, setBidderFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!project?.analysis_ready) return;
    getInsights()
      .then(setData)
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.analysis_ready]);

  const chartData = useMemo(() => {
    if (!data) return [];
    return data.ranked_totals.map((t) => ({
      bidder: t.bidder,
      total: t.grand_total ?? 0,
      isGap: t.rank === null,
      isLowest: t.rank === 1,
    }));
  }, [data]);

  const categories = useMemo(() => {
    if (!data) return [];
    const set = new Set(data.flags.map((f) => f.category));
    return Array.from(set).sort();
  }, [data]);

  const bidders = useMemo(() => {
    if (!data) return [];
    return data.ranked_totals.map((t) => t.bidder);
  }, [data]);

  const filteredFlags = useMemo(() => {
    if (!data) return [];
    const term = search.trim().toLowerCase();
    return data.flags.filter((f: Flag) => {
      if (severityFilter !== "all" && f.severity !== severityFilter) return false;
      if (categoryFilter !== "all" && f.category !== categoryFilter) return false;
      if (bidderFilter !== "all" && f.bidder !== bidderFilter) return false;
      if (term && !f.description.toLowerCase().includes(term) && !f.detail.toLowerCase().includes(term)) {
        return false;
      }
      return true;
    });
  }, [data, severityFilter, categoryFilter, bidderFilter, search]);

  const visibleFlags = filteredFlags.slice(0, 300);

  if (projectLoading) return null;
  if (!project?.analysis_ready) return <AnalysisNotAvailable project={project} />;
  if (loading) {
    return <div className="p-8 text-center text-muted-foreground animate-pulse">Loading insights...</div>;
  }
  if (!data) {
    return <div className="p-8 text-center text-muted-foreground">No data available.</div>;
  }

  const lowest = data.ranked_totals.find((t) => t.rank === 1);

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Insights Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            Headline numbers for {data.tender_no} — bidder ranking, price spread, and every
            automated flag raised
          </p>
        </div>
        <a
          href={comparisonExportUrl()}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-muted transition-colors"
        >
          <Download className="h-3.5 w-3.5" /> Download comparison report
        </a>
      </div>

      {/* Headline cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Lowest bidder</p>
            <p className="text-lg font-bold mt-1">{lowest?.bidder ?? "—"}</p>
            <p className="text-sm font-mono text-muted-foreground">AED {formatNum(lowest?.grand_total)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Contract spread</p>
            <p className="text-lg font-bold mt-1">
              {data.contract_spread ? `${(data.contract_spread.spread_pct! * 100).toFixed(0)}%` : "—"}
            </p>
            <p className="text-sm text-muted-foreground">
              {formatNum(data.contract_spread?.min)} – {formatNum(data.contract_spread?.max)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Bidders compared</p>
            <p className="text-lg font-bold mt-1">{data.ranked_totals.length}</p>
            <p className="text-sm text-muted-foreground">{Object.keys(data.data_gap_bidders).length} with data gaps</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Flags raised</p>
            <div className="flex items-center gap-2 mt-1">
              <Badge className="bg-red-600 text-white">{data.flag_summary.critical} critical</Badge>
              <Badge className="bg-amber-500 text-white">{data.flag_summary.warning} warning</Badge>
              <Badge variant="secondary">{data.flag_summary.info} info</Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bidder ranking chart */}
      <Card>
        <CardHeader>
          <CardTitle>Bidder ranking — contract total</CardTitle>
        </CardHeader>
        <CardContent>
          <div style={{ width: "100%", height: Math.max(220, chartData.length * 40) }}>
            <ResponsiveContainer>
              <BarChart data={chartData} layout="vertical" margin={{ left: 24, right: 24 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickFormatter={(v) => formatNum(v)} fontSize={11} />
                <YAxis type="category" dataKey="bidder" width={100} fontSize={12} />
                <Tooltip formatter={(v) => `AED ${formatNum(Number(v))}`} />
                <Bar dataKey="total" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.bidder}
                      fill={entry.isGap ? BAR_GAP : entry.isLowest ? BAR_LOWEST : BAR_NORMAL}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Lot spread */}
      <Card>
        <CardHeader>
          <CardTitle>Price spread by lot</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="text-left py-2 px-2">Lot</th>
                  <th className="text-right py-2 px-2">Min</th>
                  <th className="text-right py-2 px-2">Median</th>
                  <th className="text-right py-2 px-2">Max</th>
                  <th className="text-right py-2 px-2">Spread</th>
                </tr>
              </thead>
              <tbody>
                {data.lot_spread.map((l) => (
                  <tr key={l.lot_number} className="border-t border-border/60">
                    <td className="py-2 px-2">{l.lot_name}</td>
                    <td className="py-2 px-2 text-right font-mono">{formatNum(l.spread?.min)}</td>
                    <td className="py-2 px-2 text-right font-mono">{formatNum(l.spread?.median)}</td>
                    <td className="py-2 px-2 text-right font-mono">{formatNum(l.spread?.max)}</td>
                    <td className="py-2 px-2 text-right font-mono">
                      {l.spread?.spread_pct != null ? `${(l.spread.spread_pct * 100).toFixed(0)}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Flags browser */}
      <Card>
        <CardHeader>
          <CardTitle>Browse flags</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm"
            >
              <option value="all">All severities</option>
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm"
            >
              <option value="all">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABELS[c] ?? c}
                </option>
              ))}
            </select>
            <select
              value={bidderFilter}
              onChange={(e) => setBidderFilter(e.target.value)}
              className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm"
            >
              <option value="all">All bidders</option>
              {bidders.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Search description/detail..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1 min-w-[200px] rounded-lg border border-input bg-background px-3 py-1.5 text-sm"
            />
          </div>

          <p className="text-xs text-muted-foreground">
            Showing {visibleFlags.length} of {filteredFlags.length} matching flags
            {filteredFlags.length > visibleFlags.length ? " — narrow your filters to see more" : ""}
          </p>

          <div className="overflow-x-auto rounded-lg border border-border/60 max-h-[500px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted/90 backdrop-blur">
                <tr className="border-b border-border/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="text-left py-2 px-2">Severity</th>
                  <th className="text-left py-2 px-2">Category</th>
                  <th className="text-left py-2 px-2">Bidder</th>
                  <th className="text-left py-2 px-2">Lot</th>
                  <th className="text-left py-2 px-2">Item</th>
                  <th className="text-left py-2 px-2">Detail</th>
                </tr>
              </thead>
              <tbody>
                {visibleFlags.map((f, i) => (
                  <tr key={i} className="border-t border-border/60 odd:bg-muted/[0.15]">
                    <td className="py-1.5 px-2">
                      <span
                        className="inline-block w-2 h-2 rounded-full mr-1.5"
                        style={{ backgroundColor: SEVERITY_COLOR[f.severity] }}
                      />
                      {f.severity}
                    </td>
                    <td className="py-1.5 px-2">{CATEGORY_LABELS[f.category] ?? f.category}</td>
                    <td className="py-1.5 px-2">{f.bidder}</td>
                    <td className="py-1.5 px-2 text-xs">{f.lot}</td>
                    <td className="py-1.5 px-2 font-mono text-xs">{f.item_no}</td>
                    <td className="py-1.5 px-2 text-xs text-muted-foreground max-w-[400px]">{f.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
