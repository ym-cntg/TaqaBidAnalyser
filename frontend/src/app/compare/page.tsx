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
  getRounds,
  compareRound,
  type ComparisonResult,
  type ComparisonItem,
} from "@/lib/api";

function formatNum(val: number | null | undefined): string {
  if (val == null) return "-";
  return new Intl.NumberFormat("en-AE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

function getPriceColor(
  val: number | null,
  allVals: (number | null)[]
): string {
  if (val == null) return "";
  const nums = allVals.filter((v): v is number => v != null);
  if (nums.length < 2) return "";
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  if (val === min) return "text-green-600 font-semibold";
  if (val === max) return "text-red-500";
  return "";
}

export default function ComparePage() {
  const [rounds, setRounds] = useState<string[]>([]);
  const [selectedRound, setSelectedRound] = useState<string>("");
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [selectedLot, setSelectedLot] = useState<number>(1);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

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
      .then((c) => {
        setComparison(c);
        if (c.lots.length > 0) setSelectedLot(c.lots[0].lot_number);
      })
      .finally(() => setLoading(false));
  }, [selectedRound]);

  const currentLot = comparison?.lots.find((l) => l.lot_number === selectedLot);
  const bidders = currentLot
    ? Object.keys(currentLot.bidder_totals)
    : [];

  const filteredItems = currentLot?.items.filter(
    (item) =>
      !searchTerm ||
      item.item_no.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Compare Bidders
          </h1>
          <p className="text-muted-foreground mt-1">
            Side-by-side line item comparison across bidders
          </p>
        </div>
        <div className="flex gap-3">
          <Select value={selectedRound} onValueChange={(v) => v && setSelectedRound(v)}>
            <SelectTrigger className="w-40">
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
        </div>
      </div>

      {/* Lot tabs */}
      {comparison && (
        <div className="flex gap-2">
          {comparison.lots.map((lot) => (
            <button
              key={lot.lot_number}
              onClick={() => setSelectedLot(lot.lot_number)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                selectedLot === lot.lot_number
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              Lot {lot.lot_number}
            </button>
          ))}
        </div>
      )}

      {/* Lot totals */}
      {currentLot && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.entries(currentLot.bidder_totals).map(([bidder, totals]) => {
            const allTotals = Object.values(currentLot.bidder_totals)
              .map((t) => t.total)
              .filter((t): t is number => t != null);
            const isLowest =
              totals.total != null && totals.total === Math.min(...allTotals);

            return (
              <Card
                key={bidder}
                className={
                  isLowest ? "border-green-500/50 bg-green-500/5" : ""
                }
              >
                <CardContent className="pt-4">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm text-muted-foreground">{bidder}</p>
                      <p className="text-xl font-bold font-mono mt-1">
                        AED {formatNum(totals.total)}
                      </p>
                    </div>
                    <div className="text-right text-xs text-muted-foreground space-y-1">
                      <p>CIF: {formatNum(totals.cif)}</p>
                      <p>Erection: {formatNum(totals.erection)}</p>
                    </div>
                    {isLowest && (
                      <Badge className="bg-green-600 text-white">Lowest</Badge>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Search */}
      <input
        type="text"
        placeholder="Search items..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        className="w-full md:w-80 rounded-lg border border-border bg-background px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
      />

      {/* Comparison Table */}
      {loading ? (
        <div className="text-center py-12 text-muted-foreground animate-pulse">
          Loading comparison...
        </div>
      ) : (
        filteredItems && (
          <div className="rounded-lg border border-border overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/50">
                    <th className="px-3 py-3 text-left font-medium text-muted-foreground w-20 sticky left-0 bg-muted/50">
                      Item
                    </th>
                    <th className="px-3 py-3 text-left font-medium text-muted-foreground min-w-[200px]">
                      Description
                    </th>
                    <th className="px-3 py-3 text-center font-medium text-muted-foreground w-14">
                      Unit
                    </th>
                    <th className="px-3 py-3 text-right font-medium text-muted-foreground w-14">
                      Qty
                    </th>
                    {bidders.map((b) => (
                      <th
                        key={b}
                        className="px-3 py-3 text-right font-medium text-muted-foreground w-32"
                      >
                        {b}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((item: ComparisonItem, idx: number) => {
                    const totals = bidders.map(
                      (b) => item.bidder_prices[b]?.total ?? null
                    );
                    return (
                      <tr
                        key={idx}
                        className="border-t border-border hover:bg-muted/20"
                      >
                        <td className="px-3 py-2 font-mono text-xs sticky left-0 bg-background">
                          {item.item_no}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground max-w-[300px]">
                          <span className="line-clamp-1">
                            {item.description}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-center text-xs">
                          {item.unit}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs">
                          {item.qty}
                        </td>
                        {bidders.map((b, bIdx) => {
                          const val = item.bidder_prices[b]?.total;
                          return (
                            <td
                              key={b}
                              className={`px-3 py-2 text-right font-mono text-xs ${getPriceColor(val ?? null, totals)}`}
                            >
                              {formatNum(val)}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}
    </div>
  );
}
