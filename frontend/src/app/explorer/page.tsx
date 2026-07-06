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
  getBidders,
  extractBidder,
  type Bidder,
  type BOQExtraction,
  type BOQItem,
} from "@/lib/api";

function formatNum(val: number | null | undefined): string {
  if (val == null) return "-";
  return new Intl.NumberFormat("en-AE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

function formatAED(val: number | null | undefined): string {
  if (val == null) return "N/A";
  if (val >= 1_000_000) return `AED ${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `AED ${(val / 1_000).toFixed(0)}K`;
  return `AED ${val.toFixed(0)}`;
}

export default function ExplorerPage() {
  const [bidders, setBidders] = useState<Bidder[]>([]);
  const [selectedBidder, setSelectedBidder] = useState("");
  const [currentExtraction, setCurrentExtraction] = useState<BOQExtraction | null>(null);
  const [selectedLot, setSelectedLot] = useState(0);
  const [selectedSheet, setSelectedSheet] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getBidders().then((b) => {
      setBidders(b);
      if (b.length > 0) setSelectedBidder(b[0].name);
    });
  }, []);

  useEffect(() => {
    if (!selectedBidder) return;
    setLoading(true);
    extractBidder(selectedBidder)
      .then((ext) => {
        setCurrentExtraction(ext);
        setSelectedLot(0);
        setSelectedSheet(0);
      })
      .finally(() => setLoading(false));
  }, [selectedBidder]);

  const currentLot = currentExtraction?.lots[selectedLot];
  const currentSheet = currentLot?.sheets[selectedSheet];

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">BOQ Explorer</h1>
        <p className="text-muted-foreground mt-1">
          Deep dive into an individual bidder's original-round BOQ data
        </p>
      </div>

      {/* Controls */}
      <div className="flex gap-3 flex-wrap">
        <Select value={selectedBidder} onValueChange={(v) => v && setSelectedBidder(v)}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Bidder" />
          </SelectTrigger>
          <SelectContent>
            {bidders.map((b) => (
              <SelectItem key={b.name} value={b.name}>
                {b.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <div className="text-center py-12 text-muted-foreground animate-pulse">
          Loading BOQ data...
        </div>
      ) : currentExtraction ? (
        <>
          {/* Contract total */}
          <Card>
            <CardContent className="pt-4 flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">
                  {selectedBidder} — original submission
                </p>
                <p className="text-2xl font-bold font-mono">
                  {formatAED(currentExtraction.total_contract_price)}
                </p>
              </div>
              <div className="text-right text-sm text-muted-foreground">
                <p>{currentExtraction.lots.length} lots</p>
                <p>
                  {currentExtraction.lots.reduce(
                    (s, l) => s + l.total_items,
                    0
                  )}{" "}
                  total items
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Lot tabs */}
          <div className="inline-flex flex-wrap gap-1 rounded-lg bg-muted p-1">
            {currentExtraction.lots.map((lot, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setSelectedLot(idx);
                  setSelectedSheet(0);
                }}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
                  selectedLot === idx
                    ? "bg-card text-primary shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {lot.lot_name.split(":")[0]}
                <span className="ml-2 text-xs opacity-70">
                  {formatAED(lot.total_price)}
                </span>
              </button>
            ))}
          </div>

          {/* Lot summary */}
          {currentLot && (
            <div className="grid grid-cols-3 gap-4">
              <Card>
                <CardContent className="pt-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-primary/80">
                    CIF / Supply
                  </p>
                  <p className="text-lg font-bold font-mono mt-1">
                    {formatAED(currentLot.total_cif)}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-[oklch(0.55_0.14_165)]">
                    Erection
                  </p>
                  <p className="text-lg font-bold font-mono mt-1">
                    {formatAED(currentLot.total_erection)}
                  </p>
                </CardContent>
              </Card>
              <Card className="bg-primary/[0.03]">
                <CardContent className="pt-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Total (A+B)
                  </p>
                  <p className="text-lg font-bold font-mono mt-1">
                    {formatAED(currentLot.total_price)}
                  </p>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Sheet tabs */}
          {currentLot && (
            <div className="flex gap-2 border-b border-border pb-0">
              {currentLot.sheets.map((sheet, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelectedSheet(idx)}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
                    selectedSheet === idx
                      ? "border-primary text-primary"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {sheet.name.length > 25
                    ? sheet.name.slice(0, 25) + "..."
                    : sheet.name}
                  <Badge variant="secondary" className="ml-2 text-xs">
                    {sheet.item_count}
                  </Badge>
                </button>
              ))}
            </div>
          )}

          {/* Items table */}
          {currentSheet && (
            <div className="rounded-xl border border-border/60 shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/60 border-b border-border/60">
                      <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground w-20">
                        Item
                      </th>
                      <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Description
                      </th>
                      <th className="px-3 py-3 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground w-14">
                        Unit
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-14">
                        Qty
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-28">
                        CIF Rate
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-28">
                        CIF Total
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-28">
                        Erection
                      </th>
                      <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-28">
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentSheet.items.map((item: BOQItem, idx: number) => (
                      <tr
                        key={idx}
                        className={`border-t border-border/60 transition-colors ${
                          item.is_section_header
                            ? "bg-primary/[0.05] font-semibold"
                            : "odd:bg-muted/[0.15] hover:bg-primary/[0.04]"
                        }`}
                      >
                        <td className="px-3 py-2 font-mono text-xs">
                          {item.item_no}
                        </td>
                        <td
                          className="px-3 py-2 max-w-[400px]"
                          title={item.description}
                        >
                          <span className="line-clamp-2 text-xs">
                            {item.description}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-center text-xs">
                          {item.unit}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs">
                          {item.qty}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs">
                          {formatNum(item.cif_unit_rate)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs">
                          {formatNum(item.cif_total)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs">
                          {formatNum(item.erection_total)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs font-medium">
                          {formatNum(item.total)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          No data available
        </div>
      )}
    </div>
  );
}
