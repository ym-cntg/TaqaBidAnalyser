"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertTriangle,
  AlertCircle,
  Info,
  ShieldAlert,
  Calculator,
  TrendingUp,
  CircleDot,
  HelpCircle,
} from "lucide-react";
import { getRounds, compareRound, type Flag, type ComparisonResult } from "@/lib/api";

const severityConfig = {
  critical: {
    icon: ShieldAlert,
    color: "text-red-600",
    bg: "bg-red-50 border-red-200",
    badge: "bg-red-100 text-red-700",
  },
  warning: {
    icon: AlertTriangle,
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
    badge: "bg-amber-100 text-amber-700",
  },
  info: {
    icon: Info,
    color: "text-blue-600",
    bg: "bg-blue-50 border-blue-200",
    badge: "bg-blue-100 text-blue-700",
  },
};

const categoryIcons: Record<string, typeof AlertTriangle> = {
  unquoted: HelpCircle,
  arithmetic: Calculator,
  unbalanced: TrendingUp,
  outlier: CircleDot,
  missing: AlertCircle,
};

export default function FlagsPage() {
  const [rounds, setRounds] = useState<string[]>([]);
  const [selectedRound, setSelectedRound] = useState("");
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>("all");
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [filterBidder, setFilterBidder] = useState<string>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getRounds().then((r) => {
      setRounds(r);
      if (r.length > 0) setSelectedRound(r[0]);
    });
  }, []);

  useEffect(() => {
    if (!selectedRound) return;
    setLoading(true);
    compareRound(selectedRound)
      .then(setComparison)
      .finally(() => setLoading(false));
  }, [selectedRound]);

  const flags = comparison?.flags || [];
  const bidders = [
    ...new Set(flags.map((f) => f.bidder)),
  ];
  const categories = [...new Set(flags.map((f) => f.category))];

  const filtered = flags.filter((f) => {
    if (filterSeverity !== "all" && f.severity !== filterSeverity) return false;
    if (filterCategory !== "all" && f.category !== filterCategory) return false;
    if (filterBidder !== "all" && f.bidder !== filterBidder) return false;
    return true;
  });

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Flags & Insights
        </h1>
        <p className="text-muted-foreground mt-1">
          Automated detection of pricing issues, outliers, and unbalanced
          bidding
        </p>
      </div>

      {/* Summary Cards */}
      {comparison && (
        <div className="grid grid-cols-3 gap-4">
          {(["critical", "warning", "info"] as const).map((sev) => {
            const config = severityConfig[sev];
            const count =
              comparison.flag_summary[sev as keyof typeof comparison.flag_summary];
            return (
              <Card key={sev} className={config.bg}>
                <CardContent className="pt-4 flex items-center gap-4">
                  <config.icon className={`h-8 w-8 ${config.color}`} />
                  <div>
                    <p className="text-2xl font-bold">{count}</p>
                    <p className="text-sm text-muted-foreground capitalize">
                      {sev}
                    </p>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <Select value={selectedRound} onValueChange={(v) => v && setSelectedRound(v)}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Round" />
          </SelectTrigger>
          <SelectContent>
            {rounds.map((r) => (
              <SelectItem key={r} value={r}>
                {r.charAt(0).toUpperCase() + r.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filterSeverity} onValueChange={(v) => v && setFilterSeverity(v)}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Severity" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Severity</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="info">Info</SelectItem>
          </SelectContent>
        </Select>

        <Select value={filterCategory} onValueChange={(v) => v && setFilterCategory(v)}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Categories</SelectItem>
            {categories.map((c) => (
              <SelectItem key={c} value={c}>
                {c.charAt(0).toUpperCase() + c.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filterBidder} onValueChange={(v) => v && setFilterBidder(v)}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Bidder" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Bidders</SelectItem>
            {bidders.map((b) => (
              <SelectItem key={b} value={b}>
                {b}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Badge variant="secondary" className="h-9 px-3 flex items-center">
          {filtered.length} flags
        </Badge>
      </div>

      {/* Flags List */}
      {loading ? (
        <div className="text-center py-12 text-muted-foreground animate-pulse">
          Loading flags...
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.slice(0, 100).map((flag, idx) => {
            const config = severityConfig[flag.severity];
            const CategoryIcon =
              categoryIcons[flag.category] || AlertCircle;

            return (
              <div
                key={idx}
                className={`rounded-lg border p-4 ${config.bg} flex items-start gap-4`}
              >
                <CategoryIcon
                  className={`h-5 w-5 mt-0.5 ${config.color} shrink-0`}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge className={config.badge}>{flag.severity}</Badge>
                    <Badge variant="outline">{flag.category}</Badge>
                    <span className="text-sm font-medium">{flag.bidder}</span>
                    <span className="text-xs text-muted-foreground">
                      {flag.lot} - Item {flag.item_no}
                    </span>
                  </div>
                  <p className="text-sm mt-1">{flag.detail}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 truncate">
                    {flag.description}
                  </p>
                </div>
              </div>
            );
          })}
          {filtered.length > 100 && (
            <p className="text-center text-sm text-muted-foreground py-4">
              Showing 100 of {filtered.length} flags
            </p>
          )}
        </div>
      )}
    </div>
  );
}
