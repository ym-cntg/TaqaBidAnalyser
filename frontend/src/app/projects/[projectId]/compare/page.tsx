"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronRight, ChevronDown, Download, Pencil } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  getComparison,
  getBidders,
  comparisonExportUrl,
  setMatchOverride,
  clearMatchOverride,
  type ComparisonResult,
  type ComparisonItem,
} from "@/lib/api";
import { useCurrentProject } from "@/lib/project-context";
import { AnalysisNotAvailable } from "@/components/analysis-not-available";

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
  manual: { label: "Manually fixed", dot: "bg-teal-500" },
  unmatched: { label: "Unmatched", dot: "bg-red-500" },
};

interface FixerTarget {
  bidder: string;
  item: ComparisonItem;
  originalItemNo: string;
}

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
  const { project, loading: projectLoading } = useCurrentProject();
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [selectedLot, setSelectedLot] = useState<number>(1);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [highlightUnmatched, setHighlightUnmatched] = useState(false);
  const [dataGapBidders, setDataGapBidders] = useState<Set<string>>(new Set());
  const [fixerTarget, setFixerTarget] = useState<FixerTarget | null>(null);
  const [fixerSearch, setFixerSearch] = useState("");
  const [fixerBusy, setFixerBusy] = useState(false);

  useEffect(() => {
    if (!project?.analysis_ready) return;
    getComparison()
      .then((c) => {
        setComparison(c);
        if (c.lots.length > 0) setSelectedLot(c.lots[0].lot_number);
      })
      .finally(() => setLoading(false));
    getBidders().then((bidders) => {
      setDataGapBidders(new Set(bidders.filter((b) => b.data_gap).map((b) => b.name)));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.analysis_ready]);

  const currentLot = comparison?.lots.find((l) => l.lot_number === selectedLot);
  // Data-gap bidders (no real BOQ yet — see BOQ Explorer) are pushed to the
  // end rather than interleaved with real bidders, so a reviewer can see at
  // a glance which columns aren't ready to be judged against yet.
  const bidders = currentLot
    ? Object.keys(currentLot.bidder_totals).sort(
        (a, b) => Number(dataGapBidders.has(a)) - Number(dataGapBidders.has(b))
      )
    : [];
  const firstGapIndex = bidders.findIndex((b) => dataGapBidders.has(b));

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

  const fixerCandidates = useMemo(() => {
    if (!currentLot) return [];
    const term = fixerSearch.trim().toLowerCase();
    return currentLot.items
      .filter((i) => !fixerTarget || i.item_no !== fixerTarget.item.item_no)
      .filter(
        (i) =>
          !term ||
          i.item_no.toLowerCase().includes(term) ||
          i.description.toLowerCase().includes(term)
      )
      .slice(0, 50);
  }, [currentLot, fixerSearch, fixerTarget]);

  function openFixer(bidder: string, item: ComparisonItem) {
    const originalItemNo = item.bidder_prices[bidder]?.original_item_no;
    if (!originalItemNo) return;
    setFixerTarget({ bidder, item, originalItemNo });
    setFixerSearch("");
  }

  async function applyFix(targetCanonicalItemNo: string) {
    if (!fixerTarget) return;
    setFixerBusy(true);
    try {
      const updated = await setMatchOverride(
        selectedLot,
        fixerTarget.bidder,
        fixerTarget.originalItemNo,
        targetCanonicalItemNo
      );
      setComparison(updated);
      setFixerTarget(null);
    } finally {
      setFixerBusy(false);
    }
  }

  async function clearFix() {
    if (!fixerTarget) return;
    setFixerBusy(true);
    try {
      const updated = await clearMatchOverride(selectedLot, fixerTarget.bidder, fixerTarget.originalItemNo);
      setComparison(updated);
      setFixerTarget(null);
    } finally {
      setFixerBusy(false);
    }
  }

  function renderItemRow(item: ComparisonItem, indented: boolean) {
    const totals = bidders.map((b) => item.bidder_prices[b]?.total ?? null);
    // Data-gap bidders don't compete for cheapest/priciest until their BOQ
    // is actually filled in — exclude them from the comparison pool, but
    // still show whatever partial value they have (just uncolored).
    const eligibleTotals = bidders.map((b, i) => (dataGapBidders.has(b) ? null : totals[i]));
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
        {bidders.map((b, i) => {
          const isGap = dataGapBidders.has(b);
          const canFix = !!item.bidder_prices[b]?.original_item_no;
          return (
            <td
              key={b}
              className={`group/cell px-3 py-2 text-right font-mono text-xs ${
                i === firstGapIndex ? "border-l-2 border-dashed border-amber-400/50" : ""
              } ${isGap ? "text-muted-foreground/50 italic" : getPriceColor(totals[i], eligibleTotals)}`}
            >
              <span className="inline-flex items-center gap-1">
                {canFix && (
                  <button
                    onClick={() => openFixer(b, item)}
                    title={`Fix ${b}'s match for this item`}
                    className="opacity-0 group-hover/cell:opacity-100 transition-opacity text-muted-foreground hover:text-primary shrink-0"
                  >
                    <Pencil className="w-3 h-3" />
                  </button>
                )}
                <span
                  title={item.bidder_prices[b]?.is_corrected ? "Manually corrected value" : undefined}
                >
                  {formatNum(totals[i])}
                  {item.bidder_prices[b]?.is_corrected && (
                    <span className="text-amber-500 ml-0.5">*</span>
                  )}
                </span>
              </span>
            </td>
          );
        })}
      </tr>
    );
  }

  if (projectLoading) return null;
  if (!project?.analysis_ready) return <AnalysisNotAvailable project={project} />;

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Original Bid Comparison
          </h1>
          <p className="text-muted-foreground mt-1">
            Side-by-side line item comparison across bidders' original submissions
          </p>
        </div>
        <a
          href={comparisonExportUrl()}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-muted transition-colors shrink-0"
        >
          <Download className="h-3.5 w-3.5" /> Download comparison report
        </a>
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
        <div className="rounded-xl border border-border/60 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/60 border-b border-border/60">
                <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Bidder
                </th>
                <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  CIF
                </th>
                <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Erection
                </th>
                <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Total (AED)
                </th>
                <th className="px-4 py-2 w-32" />
              </tr>
            </thead>
            <tbody>
              {bidders.map((bidder) => {
                const totals = currentLot.bidder_totals[bidder];
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
                  <tr
                    key={bidder}
                    className={`border-t border-border/60 transition-colors ${
                      isLowest ? "bg-emerald-500/[0.05]" : "odd:bg-muted/[0.15]"
                    }`}
                  >
                    <td className="px-4 py-2 font-medium">{bidder}</td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">
                      {formatNum(totals.cif)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">
                      {formatNum(totals.erection)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono font-semibold">
                      {formatNum(totals.total)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {isLowest && (
                        <Badge className="bg-emerald-600 text-white text-[10px]">Lowest</Badge>
                      )}
                      {isDataGap && (
                        <Badge
                          variant="secondary"
                          className="bg-amber-500/15 text-amber-700 dark:text-amber-400 text-[10px]"
                        >
                          Data gap
                        </Badge>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Search */}
      <input
        type="text"
        placeholder="Search items..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        className="w-full md:w-80 rounded-lg border border-input bg-background px-4 py-2 text-sm shadow-sm transition-colors focus:outline-none focus:ring-3 focus:ring-ring/50 focus:border-ring"
      />

      {/* Legend — two distinct groups, since both use red/green and were
          getting visually confused: dot color = how confidently an item
          was matched across bidders; text color = how a bidder's price
          for that item compares to peers. */}
      {currentLot && (
        <div className="flex flex-wrap items-start gap-x-6 gap-y-2 rounded-lg border border-border/60 bg-muted/20 px-4 py-3 text-xs text-muted-foreground">
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-semibold text-foreground">Match quality</span>
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

          <div className="hidden md:block w-px self-stretch bg-border" />

          <div className="flex flex-wrap items-center gap-3">
            <span className="font-semibold text-foreground">Price per item</span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full bg-green-600" />
              Cheapest
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
              Priciest
            </span>
            <span className="flex items-center gap-1">
              <span className="text-amber-500 font-mono font-semibold">*</span>
              Manually corrected value
            </span>
            {dataGapBidders.size > 0 && (
              <span className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full bg-muted-foreground/40" />
                Data gap — excluded from cheapest/priciest until entered
              </span>
            )}
          </div>
        </div>
      )}

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
                    {bidders.map((b, i) => (
                      <th
                        key={b}
                        className={`px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-32 ${
                          i === firstGapIndex ? "border-l-2 border-dashed border-amber-400/50" : ""
                        }`}
                      >
                        {b}
                        {dataGapBidders.has(b) && (
                          <span className="ml-1 text-amber-500" title="Data gap — needs entry">
                            ⚠
                          </span>
                        )}
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
                    const eligibleRollupTotals = bidders.map((b, i) =>
                      dataGapBidders.has(b) ? null : rollupTotals[i]
                    );

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
                        {bidders.map((b, i) => {
                          const isGap = dataGapBidders.has(b);
                          return (
                            <td
                              key={b}
                              className={`px-3 py-2 text-right font-mono text-xs ${
                                i === firstGapIndex ? "border-l-2 border-dashed border-amber-400/50" : ""
                              } ${
                                isGap
                                  ? "text-muted-foreground/50 italic"
                                  : getPriceColor(rollupTotals[i], eligibleRollupTotals)
                              }`}
                            >
                              {formatNum(rollupTotals[i])}
                            </td>
                          );
                        })}
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

      <Dialog open={!!fixerTarget} onOpenChange={(open) => !open && setFixerTarget(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Fix item match</DialogTitle>
            <DialogDescription>
              {fixerTarget && (
                <>
                  <span className="font-medium text-foreground">{fixerTarget.bidder}</span>'s item{" "}
                  <span className="font-mono">{fixerTarget.originalItemNo}</span> is currently shown
                  under row <span className="font-mono">{fixerTarget.item.item_no}</span>. Pick the
                  correct item below to re-match it.
                </>
              )}
            </DialogDescription>
          </DialogHeader>

          <input
            type="text"
            autoFocus
            placeholder="Search item no. or description..."
            value={fixerSearch}
            onChange={(e) => setFixerSearch(e.target.value)}
            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
          />

          <div className="max-h-64 overflow-y-auto rounded-lg border border-border/60 divide-y divide-border/60">
            {fixerCandidates.length === 0 && (
              <p className="px-3 py-4 text-sm text-muted-foreground text-center">No matching items</p>
            )}
            {fixerCandidates.map((candidate) => (
              <button
                key={candidate.item_no}
                disabled={fixerBusy}
                onClick={() => applyFix(candidate.item_no)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-muted transition-colors disabled:opacity-50"
              >
                <span className="font-mono text-xs text-muted-foreground mr-2">{candidate.item_no}</span>
                <span className="line-clamp-1">{candidate.description}</span>
              </button>
            ))}
          </div>

          <DialogFooter>
            {fixerTarget?.item.match_method === "manual" && (
              <Button variant="outline" disabled={fixerBusy} onClick={clearFix}>
                Clear manual fix
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
