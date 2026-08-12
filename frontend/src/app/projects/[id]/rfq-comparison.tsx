"use client";

import { Check, Pencil, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { createCorrection, getComparison, type ComparisonLinePrice, type ComparisonResponse } from "@/lib/api";
import { formatAED, formatNumber } from "@/lib/format";
import { getCachedIdentity } from "@/lib/identity";

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

interface EditTarget {
  rfqlinenum: number;
  vendor: string;
}

export function RfqComparison({ rfqnum }: { rfqnum: string }) {
  const [data, setData] = useState<ComparisonResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const identity = getCachedIdentity();

  function load() {
    setStatus("loading");
    setError(null);
    return getComparison(rfqnum)
      .then((res) => {
        setData(res);
        setStatus("ok");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rfqnum]);

  function startEdit(rfqlinenum: number, vendor: string, currentUnitCost: number | null) {
    setEditing({ rfqlinenum, vendor });
    setEditValue(currentUnitCost != null ? String(currentUnitCost) : "");
    setEditError(null);
  }

  function cancelEdit() {
    setEditing(null);
    setEditError(null);
  }

  async function saveEdit() {
    if (!editing || !identity) return;
    const unitCost = parseFloat(editValue);
    if (Number.isNaN(unitCost) || unitCost < 0) {
      setEditError("Enter a valid price (0 or more)");
      return;
    }
    setSaving(true);
    setEditError(null);
    try {
      await createCorrection({
        rfqnum,
        rfqlinenum: editing.rfqlinenum,
        vendor: editing.vendor,
        unitCost,
        userId: identity.userId,
      });
      setEditing(null);
      // A single correction can change is_lowest/contract_total for other
      // vendors on this line too -- refetch rather than patch locally so
      // everything downstream stays correct, not just this one cell.
      await load();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

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
        (l) => String(l.rfqlinenum).includes(term) || (l.description ?? "").toLowerCase().includes(term)
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
                      {v.zero_price_count > 0 && (
                        <Badge variant="outline">
                          {v.zero_price_count} zero-priced
                        </Badge>
                      )}
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

      {!identity && (
        <p className="text-xs text-muted-foreground">
          Visit the Projects page first to identify yourself before correcting prices.
        </p>
      )}

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
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-slate-400" />
          AED 0 (likely missing)
        </span>
        <span className="flex items-center gap-1">
          <span className="text-amber-500 font-mono font-semibold">*</span>
          Manually corrected
        </span>
        {identity && (
          <span className="flex items-center gap-1">
            <Pencil className="w-3 h-3" />
            Hover a price to correct it
          </span>
        )}
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
                // Cheapest/priciest coloring excludes zero-priced and
                // unquoted cells -- same exclusion the backend already
                // applies to is_lowest, kept consistent here.
                const lineCosts = data.vendors.map((v) => {
                  const cellP = line.prices[v.vendor];
                  if (!cellP || cellP.unquoted || cellP.zero_price) return null;
                  return cellP.line_cost;
                });
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
                    {data.vendors.map((v) => (
                      <PriceCell
                        key={v.vendor}
                        p={line.prices[v.vendor]}
                        colorClass={priceColor(line.prices[v.vendor]?.line_cost ?? null, lineCosts)}
                        editable={!!identity}
                        isEditing={editing?.rfqlinenum === line.rfqlinenum && editing?.vendor === v.vendor}
                        editValue={editValue}
                        onEditValueChange={setEditValue}
                        editError={editError}
                        saving={saving}
                        onStartEdit={() => startEdit(line.rfqlinenum, v.vendor, line.prices[v.vendor]?.unit_cost ?? null)}
                        onSave={saveEdit}
                        onCancel={cancelEdit}
                      />
                    ))}
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

function PriceCell({
  p,
  colorClass,
  editable,
  isEditing,
  editValue,
  onEditValueChange,
  editError,
  saving,
  onStartEdit,
  onSave,
  onCancel,
}: {
  p: ComparisonLinePrice | undefined;
  colorClass: string;
  editable: boolean;
  isEditing: boolean;
  editValue: string;
  onEditValueChange: (v: string) => void;
  editError: string | null;
  saving: boolean;
  onStartEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  if (isEditing) {
    return (
      <td className="px-2 py-1 text-right">
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.01"
              autoFocus
              value={editValue}
              onChange={(e) => onEditValueChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSave();
                if (e.key === "Escape") onCancel();
              }}
              className="w-20 rounded border border-input bg-background px-1.5 py-0.5 text-right text-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"
            />
            <button onClick={onSave} disabled={saving} title="Save" className="text-green-600 hover:text-green-700">
              <Check className="w-3.5 h-3.5" />
            </button>
            <button onClick={onCancel} title="Cancel" className="text-muted-foreground hover:text-foreground">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          {editError && <span className="text-[10px] text-red-600 max-w-[140px] text-right">{editError}</span>}
        </div>
      </td>
    );
  }

  const empty = !p || p.unquoted;

  return (
    <td
      className={`group/cell px-3 py-2 text-right font-mono text-xs ${empty ? "text-muted-foreground/50 italic" : colorClass}`}
    >
      <span className="inline-flex items-center gap-1 justify-end">
        {editable && (
          <button
            onClick={onStartEdit}
            title="Correct this price"
            className="opacity-0 group-hover/cell:opacity-100 transition-opacity text-muted-foreground hover:text-primary shrink-0"
          >
            <Pencil className="w-3 h-3" />
          </button>
        )}
        {!empty && p!.arithmetic_error && (
          <span
            className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500 shrink-0"
            title="Arithmetic error: qty × unit rate ≠ line total"
          />
        )}
        {!empty && p!.outlier && (
          <span
            className="inline-block w-1.5 h-1.5 rounded-full bg-purple-500 shrink-0"
            title="Outlier: far from other bidders' price on this line"
          />
        )}
        {!empty && p!.zero_price && (
          <span
            className="inline-block w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0"
            title="AED 0 -- likely missing, click the pencil to correct"
          />
        )}
        <span>
          {empty ? "—" : formatAED(p!.line_cost)}
          {!empty && p!.corrected && (
            <span
              className="text-amber-500 ml-0.5"
              title={`Corrected by ${p!.corrected_by_label ?? "someone"}${p!.corrected_note ? ` — ${p!.corrected_note}` : ""}`}
            >
              *
            </span>
          )}
        </span>
      </span>
    </td>
  );
}
