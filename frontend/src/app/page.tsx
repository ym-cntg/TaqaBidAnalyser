"use client";

import { useEffect, useState, type ReactNode } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  getComparison,
  getBidders,
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

const MATCH_STYLES: Record<string, { label: string; dot: string }> = {
  exact: { label: "Exact", dot: "bg-green-500" },
  normalized: { label: "Normalized", dot: "bg-blue-500" },
  fuzzy: { label: "Fuzzy", dot: "bg-amber-500" },
  llm: { label: "AI Match", dot: "bg-purple-500" },
  unmatched: { label: "Unmatched", dot: "bg-red-500" },
};

interface ItemGroup {
  key: string;
  headerItem: ComparisonItem | null;
  children: ComparisonItem[];
}

// BOQ item numbers nest (1 -> 1.1 -> 1.1.1). Group by the top-level segment
// so long categories can be collapsed to a rolled-up row by default.
function groupByTopLevel(items: ComparisonItem[]): ItemGroup[] {
  const groups = new Map<string, ItemGroup>();
  for (const item of items) {
    const key = item.item_no.split(".")[0];
    if (!groups.has(key)) {
      groups.set(key, { key, headerItem: null, children: [] });
    }
    const group = groups.get(key)!;
    if (item.item_no === key) {
      group.headerItem = item;
    } else {
      group.children.push(item);
    }
  }
  return Array.from(groups.values());
}

// Roll up a group's per-bidder totals by summing its children (the header
// row itself is a category label, not usually priced on its own).
function rollupTotal(group: ItemGroup, bidder: string): number | null {
  const source = group.children.length > 0 ? group.children : group.headerItem ? [group.headerItem] : [];
  const values = source
    .map((item) => item.bidder_prices[bidder]?.total)
    .filter((v): v is number => v != null);
  return values.length > 0 ? values.reduce((a, b) => a + b, 0) : null;
}

export default function ComparePage() {
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [selectedLot, setSelectedLot] = useState<number>(1);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [highlightUnmatched, setHighlightUnmatched] = useState(false);
  const [dataGapBidders, setDataGapBidders] = useState<Set<string>>(new Set());

  useEffect(() => {
    getComparison()
      .then((c) => {
        setComparison(c);
        if (c.lots.length > 0) setSelectedLot(c.lots[0].lot_number);
      })
      .finally(() => setLoading(false));
    getBidders().then((bidders) => {
      setDataGapBidders(new Set(bidders.filter((b) => b.data_gap).map((b) => b.name)));
    });
  }, []);

  const currentLot = comparison?.lots.find((l) => l.lot_number === selectedLot);
  const bidders = currentLot ? Object.keys(currentLot.bidder_totals) : [];

  const isSearching = searchTerm.trim().length > 0;
  const matchesSearch = (item: ComparisonItem) =>
    item.item_no.toLowerCase().includes(searchTerm.toLowerCase()) ||
    item.description.toLowerCase().includes(searchTerm.toLowerCase());

  const groups = currentLot ? groupByTopLevel(currentLot.items) : [];

  function toggleGroup(key: string) {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function renderItemRow(item: ComparisonItem, indented: boolean) {
    const totals = bidders.map((b) => item.bidder_prices[b]?.total ?? null);
    const isHighlighted = highlightUnmatched && item.match_method === "unmatched";
    return (
      <tr
        key={item.item_no}
        className={`border-t transition-colors ${
          isHighlighted
            ? "border-red-500/30 bg-red-500/[0.08] hover:bg-red-500/[0.12]"
            : "border-border/60 odd:bg-muted/[0.15] hover:bg-primary/[0.04]"
        }`}
      >
        <td
          className={`px-3 py-2 font-mono text-xs sticky left-0 ${
            isHighlighted ? "bg-[oklch(0.97_0.02_25)] dark:bg-[oklch(0.28_0.05_25)]" : "bg-card"
          }`}
        >
          <span className={`flex items-center gap-1.5 ${indented ? "pl-4" : ""}`}>
            <span className="relative group">
              <span
                className={`inline-block w-2 h-2 rounded-full flex-shrink-0 cursor-help ${MATCH_STYLES[item.match_method]?.dot ?? ""}`}
              />
              <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 rounded text-[10px] font-sans whitespace-nowrap bg-foreground text-background opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                {MATCH_STYLES[item.match_method]?.label ?? item.match_method} ({Math.round(item.match_confidence * 100)}%)
              </span>
            </span>
            {item.item_no}
          </span>
        </td>
        <td className="px-3 py-2 text-muted-foreground max-w-[300px]">
          <span className="line-clamp-1">{item.description}</span>
        </td>
        <td className="px-3 py-2 text-center text-xs">{item.unit}</td>
        <td className="px-3 py-2 text-right font-mono text-xs">{item.qty}</td>
        {bidders.map((b, i) => (
          <td
            key={b}
            className={`px-3 py-2 text-right font-mono text-xs ${getPriceColor(totals[i], totals)}`}
          >
            <span
              title={item.bidder_prices[b]?.is_corrected ? "Manually corrected value" : undefined}
            >
              {formatNum(totals[i])}
              {item.bidder_prices[b]?.is_corrected && (
                <span className="text-amber-500 ml-0.5">*</span>
              )}
            </span>
          </td>
        ))}
      </tr>
    );
  }

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Original Bid Comparison
        </h1>
        <p className="text-muted-foreground mt-1">
          Side-by-side line item comparison across bidders' original submissions
        </p>
      </div>

      {/* Lot tabs */}
      {comparison && (
        <div className="inline-flex gap-1 rounded-lg bg-muted p-1">
          {comparison.lots.map((lot) => (
            <button
              key={lot.lot_number}
              onClick={() => setSelectedLot(lot.lot_number)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
                selectedLot === lot.lot_number
                  ? "bg-card text-primary shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
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
            const isDataGap = dataGapBidders.has(bidder);
            // A data-gap bidder's total may be partially (or not at all) manually
            // entered — it's never a fair basis for "Lowest" until the reviewer
            // has filled in the whole BOQ, so exclude it from the ranking pool
            // entirely rather than letting an incomplete total win by default.
            const allTotals = Object.entries(currentLot.bidder_totals)
              .filter(([b]) => !dataGapBidders.has(b))
              .map(([, t]) => t.total)
              .filter((t): t is number => t != null);
            const isLowest =
              !isDataGap && totals.total != null && totals.total === Math.min(...allTotals);

            return (
              <Card
                key={bidder}
                className={
                  isLowest
                    ? "border-emerald-500/40 bg-emerald-500/[0.06] shadow-sm shadow-emerald-500/10"
                    : ""
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
                      <Badge className="bg-emerald-600 text-white">
                        Lowest
                      </Badge>
                    )}
                    {isDataGap && (
                      <Badge
                        variant="secondary"
                        className="bg-amber-500/15 text-amber-700 dark:text-amber-400"
                      >
                        Data gap — needs entry
                      </Badge>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Search + Match Legend */}
      <div className="flex flex-wrap items-center gap-4">
        <input
          type="text"
          placeholder="Search items..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full md:w-80 rounded-lg border border-input bg-background px-4 py-2 text-sm shadow-sm transition-colors focus:outline-none focus:ring-3 focus:ring-ring/50 focus:border-ring"
        />
        {currentLot && (
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="font-medium">Match quality:</span>
            {Object.entries(MATCH_STYLES).map(([key, style]) => {
              const count = currentLot.items.filter((i) => i.match_method === key).length;
              if (count === 0) return null;

              if (key === "unmatched") {
                return (
                  <button
                    key={key}
                    onClick={() => setHighlightUnmatched((v) => !v)}
                    className={`flex items-center gap-1 rounded-full px-2 py-1 transition-colors ${
                      highlightUnmatched
                        ? "bg-red-500/15 text-red-700 dark:text-red-400 ring-1 ring-red-500/40"
                        : "hover:bg-muted"
                    }`}
                    title={highlightUnmatched ? "Click to stop highlighting" : "Click to highlight unmatched items"}
                  >
                    <span className={`inline-block w-2 h-2 rounded-full ${style.dot}`} />
                    {style.label} ({count})
                  </button>
                );
              }

              return (
                <span key={key} className="flex items-center gap-1">
                  <span className={`inline-block w-2 h-2 rounded-full ${style.dot}`} />
                  {style.label} ({count})
                </span>
              );
            })}
          </div>
        )}
      </div>

      {/* Comparison Table */}
      {loading ? (
        <div className="text-center py-12 text-muted-foreground animate-pulse">
          Loading comparison...
        </div>
      ) : (
        currentLot && (
          <div className="rounded-xl border border-border/60 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/60 border-b border-border/60">
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground w-20 sticky left-0 bg-muted/60">
                      Item
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground min-w-[200px]">
                      Description
                    </th>
                    <th className="px-3 py-3 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground w-14">
                      Unit
                    </th>
                    <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-14">
                      Qty
                    </th>
                    {bidders.map((b) => (
                      <th
                        key={b}
                        className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-32"
                      >
                        {b}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {groups.flatMap((group): ReactNode[] => {
                    // A group with no dotted children is just a single line
                    // item — render it flat, no dropdown needed.
                    if (group.children.length === 0) {
                      if (group.headerItem && (!isSearching || matchesSearch(group.headerItem))) {
                        return [renderItemRow(group.headerItem, false)];
                      }
                      return [];
                    }

                    const visibleChildren = isSearching
                      ? group.children.filter(matchesSearch)
                      : group.children;
                    const headerMatches = isSearching && group.headerItem && matchesSearch(group.headerItem);
                    if (isSearching && visibleChildren.length === 0 && !headerMatches) {
                      return [];
                    }
                    const hasUnmatchedChild = group.children.some((c) => c.match_method === "unmatched");
                    const isExpanded = isSearching
                      ? true
                      : expandedGroups.has(group.key) || (highlightUnmatched && hasUnmatchedChild);
                    const rollupTotals = bidders.map((b) => rollupTotal(group, b));

                    const headerRow = (
                      <tr
                        key={`group-${group.key}`}
                        onClick={() => toggleGroup(group.key)}
                        className="border-t border-border/60 bg-primary/[0.04] hover:bg-primary/[0.08] cursor-pointer transition-colors font-medium"
                      >
                        <td className="px-3 py-2 font-mono text-xs sticky left-0 bg-[oklch(0.97_0.01_224)] dark:bg-[oklch(0.24_0.03_224)]">
                          <span className="flex items-center gap-1">
                            {isExpanded ? (
                              <ChevronDown className="w-3.5 h-3.5 text-primary shrink-0" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5 text-primary shrink-0" />
                            )}
                            {group.key}
                          </span>
                        </td>
                        <td className="px-3 py-2 max-w-[300px]">
                          <span className="line-clamp-1">
                            {group.headerItem?.description || `Item ${group.key}`}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-center text-xs text-muted-foreground">
                          -
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs text-muted-foreground">
                          -
                        </td>
                        {bidders.map((b, i) => (
                          <td
                            key={b}
                            className={`px-3 py-2 text-right font-mono text-xs ${getPriceColor(rollupTotals[i], rollupTotals)}`}
                          >
                            {formatNum(rollupTotals[i])}
                          </td>
                        ))}
                      </tr>
                    );

                    return isExpanded
                      ? [headerRow, ...visibleChildren.map((item) => renderItemRow(item, true))]
                      : [headerRow];
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
