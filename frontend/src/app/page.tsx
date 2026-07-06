"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Users,
  FileSpreadsheet,
  TrendingDown,
  AlertTriangle,
} from "lucide-react";
import {
  getBidders,
  getRounds,
  compareRound,
  extractBidder,
  type Bidder,
  type ComparisonResult,
  type BOQExtraction,
} from "@/lib/api";
import { PriceChart } from "@/components/price-chart";

function formatAED(val: number | null | undefined): string {
  if (val == null) return "N/A";
  if (val >= 1_000_000) return `AED ${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `AED ${(val / 1_000).toFixed(0)}K`;
  return `AED ${val.toFixed(0)}`;
}

export default function Dashboard() {
  const [bidders, setBidders] = useState<Bidder[]>([]);
  const [rounds, setRounds] = useState<string[]>([]);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [allExtractions, setAllExtractions] = useState<
    Record<string, BOQExtraction[]>
  >({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [b, r] = await Promise.all([getBidders(), getRounds()]);
        setBidders(b);
        setRounds(r);

        if (r.length > 0) {
          const comp = await compareRound(r[0]);
          setComparison(comp);
        }

        const extractions: Record<string, BOQExtraction[]> = {};
        for (const bidder of b) {
          extractions[bidder.name] = await extractBidder(bidder.name);
        }
        setAllExtractions(extractions);
      } catch (err) {
        console.error("Failed to load dashboard data:", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-pulse text-muted-foreground">
          Loading bid data...
        </div>
      </div>
    );
  }

  const totalItems = comparison
    ? comparison.lots.reduce((sum, lot) => sum + lot.item_count, 0)
    : 0;

  return (
    <div className="p-8 space-y-8">
      <div className="flex items-center justify-between rounded-2xl border border-border/60 bg-gradient-to-r from-primary/10 via-card to-card px-6 py-5 shadow-sm">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">
            Tender D-111808
          </p>
          <h1 className="text-2xl font-bold tracking-tight mt-0.5">
            Bid Analysis Dashboard
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Construction Works for Replacement of SHBPRY, SMHPRY and DRPRY
            Substations — ADDC Eastern Region
          </p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Bidders
            </CardTitle>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
              <Users className="h-4 w-4 text-primary" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{bidders.length}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {bidders.map((b) => b.name).join(", ")}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Negotiation Rounds
            </CardTitle>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[oklch(0.7_0.15_165)]/15">
              <TrendingDown className="h-4 w-4 text-[oklch(0.55_0.14_165)]" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{rounds.length}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {rounds.join(", ")}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              BOQ Line Items
            </CardTitle>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/10">
              <FileSpreadsheet className="h-4 w-4 text-violet-600" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalItems}</div>
            <p className="text-xs text-muted-foreground mt-1">
              Across {comparison?.lots.length || 0} lots
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Flags Detected
            </CardTitle>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/10">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {comparison?.flag_summary
                ? comparison.flag_summary.critical +
                  comparison.flag_summary.warning
                : 0}
            </div>
            <div className="flex gap-2 mt-1">
              {comparison?.flag_summary.critical ? (
                <Badge variant="destructive" className="text-xs">
                  {comparison.flag_summary.critical} critical
                </Badge>
              ) : null}
              {comparison?.flag_summary.warning ? (
                <Badge variant="secondary" className="text-xs">
                  {comparison.flag_summary.warning} warnings
                </Badge>
              ) : null}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Price Chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            Total Contract Price by Round
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PriceChart extractions={allExtractions} />
        </CardContent>
      </Card>

      {/* Lot Summary + Grand Totals */}
      {comparison && (
        <>
          <div>
            <h2 className="text-lg font-semibold mb-4">
              Lot Summary — {comparison.round_name}
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {comparison.lots.map((lot) => (
                <Card key={lot.lot_number}>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium">
                      {lot.lot_name}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {Object.entries(lot.bidder_totals).map(
                      ([bidder, totals]) => (
                        <div
                          key={bidder}
                          className="flex items-center justify-between"
                        >
                          <span className="text-sm text-muted-foreground">
                            {bidder}
                          </span>
                          <span className="text-sm font-mono font-medium">
                            {formatAED(totals.total)}
                          </span>
                        </div>
                      )
                    )}
                    <div className="pt-2 border-t border-border">
                      <p className="text-xs text-muted-foreground">
                        {lot.item_count} line items compared
                      </p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">
                Grand Total — {comparison.round_name}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {Object.entries(comparison.bidder_grand_totals).map(
                  ([bidder, total]) => {
                    const allTotals = Object.values(
                      comparison.bidder_grand_totals
                    ).filter((t): t is number => t != null);
                    const minTotal = Math.min(...allTotals);
                    const isLowest = total === minTotal;

                    return (
                      <div
                        key={bidder}
                        className={`rounded-xl border p-6 transition-shadow ${
                          isLowest
                            ? "border-emerald-500/40 bg-emerald-500/[0.06] shadow-sm shadow-emerald-500/10"
                            : "border-border/60"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <h3 className="font-semibold">{bidder}</h3>
                          {isLowest && (
                            <Badge className="bg-emerald-600 text-white text-xs">
                              Lowest
                            </Badge>
                          )}
                        </div>
                        <p className="text-3xl font-bold font-mono">
                          {formatAED(total)}
                        </p>
                        {total && minTotal && !isLowest && (
                          <p className="text-sm text-muted-foreground mt-1">
                            +{formatAED(total - minTotal)} (
                            {(((total - minTotal) / minTotal) * 100).toFixed(1)}
                            % higher)
                          </p>
                        )}
                      </div>
                    );
                  }
                )}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
