"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { getComparison, type ComparisonResponse } from "@/lib/api";
import { formatAED, formatNumber } from "@/lib/format";

function vendorLabel(vendor: string, name: string | null): string {
  return name ?? vendor;
}

// Cheapest/priciest per line, styled the same way the original build did:
// text color on the value itself, not a cell background -- green for the
// lowest quote on a line, red for the highest, nothing for the rest.
function priceColor(val: number | null, allVals: (number | null)[]): string {
  if (val == null) return "";
  const nums = allVals.filter((v): v is number => v != null);
  if (nums.length < 2) return "";
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  if (val === min) return "text-green-600 font-semibold";
  if (val === max) return "text-red-500";
  return "";
}

export function RfqComparison({ rfqnum }: { rfqnum: string }) {
  const [data, setData] = useState<ComparisonResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    setStatus("loading");
    setError(null);
    getComparison(rfqnum)
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
    return <div className="text-center py-12 text-muted-foreground animate-pulse">Loading comparison…</div>;
  }

  if (status === "error") {
    return (
      <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-600">{error}</div>
    );
  }

  if (!data) return null;

  if (data.vendors.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">No vendor pricing found for this RFQ yet.</div>
    );
  }

  const contractTotals = data.vendors.map((v) => v.contract_total);
  const lowestTotal = Math.min(...contractTotals);

  const term = search.trim().toLowerCase();
  const isSearching = term.length > 0;
  const visibleLines = isSearching
    ? data.lines.filter(
        (l) =>
          String(l.rfqlinenum).includes(term) || (l.description ?? "").toLowerCase().includes(term)
      )
    : data.lines;

  return (
    <div className="space-y-6">
      {/* Contract totals */}
      <div className="rounded-xl border border-border/60 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/60 border-b border-border/60">
              <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Vendor
              </th>
              <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Contract total
              </th>
              <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Flags
              </th>
            </tr>
          </thead>
          <tbody>
            {data.vendors.map((v) => {
              const isLowest = v.contract_total === lowestTotal;
              return (
                <tr
                  key={v.vendor}
                  className={`border-t border-border/60 transition-colors ${
                    isLowest ? "bg-emerald-500/[0.05]" : "odd:bg-muted/[0.15]"
                  }`}
                >
                  <td className="px-4 py-2">
                    <div className="font-medium">{vendorLabel(v.vendor, v.name)}</div>
                    <div className="font-mono text-xs text-muted-foreground">{v.vendor}</div>
                  </td>
                  <td className="px-4 py-2 text-right font-mono font-semibold">{formatAED(v.contract_total)}</td>
                  <td className="px-4 py-2">
                    <div className="flex flex-wrap gap-1">
                      {isLowest && <Badge className="bg-emerald-600 text-white text-[10px]">Lowest</Badge>}
                      {v.unquoted_count > 0 && <Badge variant="outline">{v.unquoted_count} unquoted</Badge>}
                      {v.arithmetic_error_count > 0 && (
                        <Badge variant="destructive">
                          {v.arithmetic_error_count} arithmetic error{v.arithmetic_error_count > 1 ? "s" : ""}
                        </Badge>
                      )}
                      {v.outlier_count > 0 && (
                        <Badge variant="secondary">
                          {v.outlier_count} outlier{v.outlier_count > 1 ? "s" : ""}
                        </Badge>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {data.not_submitted.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Invited but did not submit any pricing:{" "}
          {data.not_submitted.map((v) => vendorLabel(v.vendor, v.name)).join(", ")}
        </p>
      )}

      {/* Search */}
      <input
        type="text"
        placeholder="Search line number or description…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full md:w-80 rounded-lg border border-input bg-background px-4 py-2 text-sm shadow-sm transition-colors focus:outline-none focus:ring-3 focus:ring-ring/50 focus:border-ring"
      />

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-border/60 bg-muted/20 px-4 py-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-green-600" />
          Cheapest on line
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
          Priciest on line
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-orange-500" />
          Arithmetic error (qty × unit rate ≠ line total)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-purple-500" />
          Outlier (far from other bidders on this line)
        </span>
      </div>

      {data.truncated && (
        <p className="text-xs text-muted-foreground">
          Showing first {data.lines.length.toLocaleString()} of {data.total_line_count.toLocaleString()} lines.
        </p>
      )}

      {/* Line-item comparison */}
      <div className="rounded-xl border border-border/60 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/60 border-b border-border/60">
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground w-20 sticky left-0 bg-muted/60">
                  Line
                </th>
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground min-w-[240px]">
                  Description
                </th>
                <th className="px-3 py-3 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground w-14">
                  Unit
                </th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-16">
                  Qty
                </th>
                {data.vendors.map((v) => (
                  <th
                    key={v.vendor}
                    className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-32"
                  >
                    {vendorLabel(v.vendor, v.name)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleLines.map((line) => {
                const lineCosts = data.vendors.map((v) => line.prices[v.vendor]?.line_cost ?? null);
                return (
                  <tr
                    key={line.rfqlinenum}
                    className="border-t border-border/60 odd:bg-muted/[0.15] hover:bg-primary/[0.04] transition-colors"
                  >
                    <td className="px-3 py-2 font-mono text-xs sticky left-0 bg-card">{line.rfqlinenum}</td>
                    <td className="px-3 py-2 text-muted-foreground max-w-[300px]">
                      <span className="line-clamp-1">{line.description ?? "—"}</span>
                    </td>
                    <td className="px-3 py-2 text-center text-xs">{line.unit ?? "—"}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs">
                      {line.qty != null ? formatNumber(line.qty) : "—"}
                    </td>
                    {data.vendors.map((v) => {
                      const p = line.prices[v.vendor];
                      if (!p || p.unquoted) {
                        return (
                          <td
                            key={v.vendor}
                            className="px-3 py-2 text-right font-mono text-xs text-muted-foreground/50 italic"
                          >
                            —
                          </td>
                        );
                      }
                      return (
                        <td
                          key={v.vendor}
                          className={`px-3 py-2 text-right font-mono text-xs ${priceColor(p.line_cost, lineCosts)}`}
                        >
                          <span className="inline-flex items-center gap-1 justify-end">
                            {p.arithmetic_error && (
                              <span
                                className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500 shrink-0"
                                title="Arithmetic error: qty × unit rate ≠ line total"
                              />
                            )}
                            {p.outlier && (
                              <span
                                className="inline-block w-1.5 h-1.5 rounded-full bg-purple-500 shrink-0"
                                title="Outlier: far from other bidders' price on this line"
                              />
                            )}
                            {formatAED(p.line_cost)}
                          </span>
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
    </div>
  );
}
