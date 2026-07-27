"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Pencil, Check, X, Undo2, AlertTriangle, Sparkles } from "lucide-react";
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
  correctItem,
  revertItem,
  getRecommendations,
  type Bidder,
  type BOQExtraction,
  type BOQItem,
  type EditableItemField,
  type Recommendation,
} from "@/lib/api";
import { useCurrentProject } from "@/lib/project-context";
import { AnalysisNotAvailable } from "@/components/analysis-not-available";

const EDITABLE_TEXT_FIELDS: EditableItemField[] = ["description", "unit"];
const EDITABLE_NUMERIC_FIELDS: EditableItemField[] = [
  "qty",
  "cif_unit_rate",
  "cif_total",
  "erection_unit_rate",
  "erection_total",
];

function itemToEditValues(item: BOQItem): Record<string, string> {
  return {
    description: item.description ?? "",
    unit: item.unit ?? "",
    qty: item.qty?.toString() ?? "",
    cif_unit_rate: item.cif_unit_rate?.toString() ?? "",
    cif_total: item.cif_total?.toString() ?? "",
    erection_unit_rate: item.erection_unit_rate?.toString() ?? "",
    erection_total: item.erection_total?.toString() ?? "",
  };
}

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
  const { project, loading: projectLoading } = useCurrentProject();
  const [bidders, setBidders] = useState<Bidder[]>([]);
  const [selectedBidder, setSelectedBidder] = useState("");
  const [currentExtraction, setCurrentExtraction] = useState<BOQExtraction | null>(null);
  const [selectedLot, setSelectedLot] = useState(0);
  const [selectedSheet, setSelectedSheet] = useState(0);
  const [loading, setLoading] = useState(true);
  const [editingItemNo, setEditingItemNo] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [savingItemNo, setSavingItemNo] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Record<string, Recommendation>>({});

  useEffect(() => {
    if (!project?.analysis_ready) return;
    getBidders().then((b) => {
      setBidders(b);
      if (b.length > 0) setSelectedBidder(b[0].name);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.analysis_ready]);

  useEffect(() => {
    if (!selectedBidder) return;
    setLoading(true);
    setRecommendations({});
    extractBidder(selectedBidder)
      .then((ext) => {
        setCurrentExtraction(ext);
        setSelectedLot(0);
        setSelectedSheet(0);
        if (ext.data_gap) {
          getRecommendations(selectedBidder)
            .then(setRecommendations)
            .catch(() => setRecommendations({}));
        }
      })
      .finally(() => setLoading(false));
  }, [selectedBidder]);

  function startEdit(item: BOQItem) {
    setSaveError(null);
    setEditingItemNo(item.item_no);
    setEditValues(itemToEditValues(item));
  }

  function applyRecommendation(lotNumber: number, itemNo: string) {
    const rec = recommendations[`${lotNumber}:${itemNo}`];
    if (!rec) return;
    setEditValues((v) => ({
      ...v,
      cif_total: String(Math.round(rec.recommended_cif_total)),
      erection_total: String(Math.round(rec.recommended_erection_total)),
    }));
  }

  function cancelEdit() {
    setEditingItemNo(null);
    setEditValues({});
    setSaveError(null);
  }

  async function saveEdit(item: BOQItem, lotNumber: number, sheetName: string) {
    const before = itemToEditValues(item);
    const fields: Record<string, string | number | null> = {};

    for (const key of EDITABLE_TEXT_FIELDS) {
      const next = editValues[key] ?? "";
      if (next !== before[key]) fields[key] = next;
    }
    for (const key of EDITABLE_NUMERIC_FIELDS) {
      const raw = (editValues[key] ?? "").trim();
      const beforeRaw = before[key] ?? "";
      if (raw === beforeRaw) continue;
      if (raw === "") {
        fields[key] = null;
        continue;
      }
      const num = Number(raw);
      if (Number.isNaN(num)) {
        setSaveError(`"${raw}" isn't a valid number for ${key}`);
        return;
      }
      fields[key] = num;
    }

    if (Object.keys(fields).length === 0) {
      cancelEdit();
      return;
    }

    setSavingItemNo(item.item_no);
    setSaveError(null);
    try {
      const updated = await correctItem(selectedBidder, lotNumber, sheetName, item.item_no, fields);
      setCurrentExtraction(updated);
      cancelEdit();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to save correction");
    } finally {
      setSavingItemNo(null);
    }
  }

  async function handleRevert(item: BOQItem, lotNumber: number, sheetName: string) {
    setSavingItemNo(item.item_no);
    setSaveError(null);
    try {
      const updated = await revertItem(selectedBidder, lotNumber, sheetName, item.item_no);
      setCurrentExtraction(updated);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to revert correction");
    } finally {
      setSavingItemNo(null);
    }
  }

  const currentLot = currentExtraction?.lots[selectedLot];
  const currentSheet = currentLot?.sheets[selectedSheet];

  if (projectLoading) return null;
  if (!project?.analysis_ready) return <AnalysisNotAvailable project={project} />;

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
                {b.data_gap ? " ⚠" : ""}
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
          {currentExtraction.data_gap && (
            <div className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
              <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0 text-amber-600" />
              <div>
                <p className="font-medium text-amber-800 dark:text-amber-400">
                  Data gap — no per-item BOQ was extractable for this bidder
                </p>
                <p className="text-muted-foreground mt-0.5">{currentExtraction.data_gap}</p>
                <p className="text-muted-foreground mt-1">
                  Rows below are the standard item template with prices missing. Click{" "}
                  <Pencil className="inline h-3 w-3 mx-0.5" /> on a row to enter it manually —{" "}
                  <Sparkles className="inline h-3 w-3 mx-0.5 text-amber-600" /> pre-fills a
                  peer-median suggestion where available, which you can accept or adjust.
                </p>
              </div>
            </div>
          )}

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
          {currentSheet && currentLot && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Spot an OCR/parsing mistake? Click <Pencil className="inline h-3 w-3 mx-0.5" />{" "}
                on a row to correct it — the fix flows straight into totals, flags, and the
                Compare table.
              </p>
              {saveError && (
                <div className="text-xs text-destructive bg-destructive/10 border border-destructive/30 rounded-md px-3 py-2">
                  {saveError}
                </div>
              )}
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
                        <th className="px-3 py-3 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground w-20">
                          Review
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {currentSheet.items.map((item: BOQItem, idx: number) => {
                        const isEditing = editingItemNo === item.item_no;
                        const isSaving = savingItemNo === item.item_no;

                        if (isEditing) {
                          return (
                            <tr
                              key={idx}
                              className="border-t border-border/60 bg-primary/[0.06]"
                            >
                              <td className="px-3 py-2 font-mono text-xs">
                                {item.item_no}
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                                  value={editValues.description ?? ""}
                                  onChange={(e) =>
                                    setEditValues((v) => ({ ...v, description: e.target.value }))
                                  }
                                />
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  className="w-14 rounded border border-border bg-background px-1 py-1 text-xs text-center"
                                  value={editValues.unit ?? ""}
                                  onChange={(e) =>
                                    setEditValues((v) => ({ ...v, unit: e.target.value }))
                                  }
                                />
                              </td>
                              {(["qty", "cif_unit_rate", "cif_total", "erection_total"] as const).map(
                                (field) => (
                                  <td className="px-2 py-2" key={field}>
                                    <input
                                      className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-right font-mono"
                                      inputMode="decimal"
                                      value={editValues[field] ?? ""}
                                      onChange={(e) =>
                                        setEditValues((v) => ({ ...v, [field]: e.target.value }))
                                      }
                                    />
                                  </td>
                                )
                              )}
                              <td className="px-3 py-2 text-right font-mono text-xs text-muted-foreground">
                                auto
                              </td>
                              <td className="px-2 py-2">
                                <div className="flex items-center justify-center gap-1.5">
                                  {recommendations[`${currentLot.lot_number}:${item.item_no}`] && (
                                    <button
                                      disabled={isSaving}
                                      onClick={() =>
                                        applyRecommendation(currentLot.lot_number, item.item_no)
                                      }
                                      className="p-1 rounded hover:bg-amber-500/10 text-amber-600 disabled:opacity-50"
                                      title={`Use peer-median suggestion (from ${
                                        recommendations[`${currentLot.lot_number}:${item.item_no}`]
                                          .peer_count
                                      } bidders)`}
                                    >
                                      <Sparkles className="h-3.5 w-3.5" />
                                    </button>
                                  )}
                                  <button
                                    disabled={isSaving}
                                    onClick={() =>
                                      saveEdit(item, currentLot.lot_number, currentSheet.name)
                                    }
                                    className="p-1 rounded hover:bg-primary/10 text-primary disabled:opacity-50"
                                    title="Save"
                                  >
                                    <Check className="h-3.5 w-3.5" />
                                  </button>
                                  <button
                                    disabled={isSaving}
                                    onClick={cancelEdit}
                                    className="p-1 rounded hover:bg-muted text-muted-foreground disabled:opacity-50"
                                    title="Cancel"
                                  >
                                    <X className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        }

                        return (
                          <tr
                            key={idx}
                            className={`border-t border-border/60 transition-colors ${
                              item.is_section_header
                                ? "bg-primary/[0.05] font-semibold"
                                : item.is_missing
                                  ? "bg-red-500/[0.06] hover:bg-red-500/[0.1]"
                                  : item.is_corrected
                                    ? "bg-amber-500/[0.07] hover:bg-amber-500/[0.12]"
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
                              {item.is_corrected && (
                                <Badge
                                  variant="secondary"
                                  className="ml-2 text-[10px] bg-amber-500/15 text-amber-700 dark:text-amber-400"
                                >
                                  Corrected
                                </Badge>
                              )}
                              {item.is_missing && (
                                <Badge
                                  variant="secondary"
                                  className="ml-2 text-[10px] bg-red-500/15 text-red-700 dark:text-red-400"
                                >
                                  Needs entry
                                </Badge>
                              )}
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
                            <td className="px-2 py-2">
                              {!item.is_section_header && (
                                <div className="flex items-center justify-center gap-1.5">
                                  <button
                                    onClick={() => startEdit(item)}
                                    className="p-1 rounded hover:bg-primary/10 text-muted-foreground hover:text-primary"
                                    title="Edit"
                                  >
                                    <Pencil className="h-3.5 w-3.5" />
                                  </button>
                                  {item.is_corrected && (
                                    <button
                                      disabled={isSaving}
                                      onClick={() =>
                                        handleRevert(item, currentLot.lot_number, currentSheet.name)
                                      }
                                      className="p-1 rounded hover:bg-muted text-amber-600 disabled:opacity-50"
                                      title="Revert to extracted value"
                                    >
                                      <Undo2 className="h-3.5 w-3.5" />
                                    </button>
                                  )}
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
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
