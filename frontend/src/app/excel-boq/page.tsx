"use client";

import Link from "next/link";
import { useCallback, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  exportExcelBoq,
  parseExcelBoq,
  type BoqLine,
  type ParsedBoq,
} from "@/lib/api";
import { formatNumber } from "@/lib/format";

// Same principle as every other page here: show the backend's real
// error text, never a guessed explanation derived from matching on the
// message string.

const PREVIEW_LINES = 300;

function money(value: number | null): string {
  if (value == null) return "";
  return formatNumber(value);
}

function lineLabel(line: BoqLine): string {
  return line.item_no ? `${line.item_no}` : "";
}

export default function ExcelBoqPage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ParsedBoq | null>(null);
  const [status, setStatus] = useState<"idle" | "parsing" | "exporting">("idle");
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [activeSheet, setActiveSheet] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (picked: File) => {
    setFile(picked);
    setResult(null);
    setError(null);
    setActiveSheet(0);
    setStatus("parsing");
    try {
      const parsed = await parseExcelBoq(picked);
      setResult(parsed);
      const firstBoq = parsed.sheets.findIndex((s) => s.role === "boq");
      setActiveSheet(firstBoq >= 0 ? firstBoq : 0);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setStatus("idle");
    }
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setDragging(false);
      const dropped = event.dataTransfer.files?.[0];
      if (dropped) void handleFile(dropped);
    },
    [handleFile],
  );

  const onExport = useCallback(async () => {
    if (!file) return;
    setStatus("exporting");
    setError(null);
    try {
      const { blob, filename } = await exportExcelBoq(file);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setStatus("idle");
    }
  }, [file]);

  const sheet = result?.sheets[activeSheet] ?? null;
  const visibleLines = useMemo(
    () => (sheet ? sheet.lines.filter((l) => l.kind !== "note").slice(0, PREVIEW_LINES) : []),
    [sheet],
  );
  const hiddenCount = useMemo(
    () => (sheet ? Math.max(0, sheet.lines.filter((l) => l.kind !== "note").length - PREVIEW_LINES) : 0),
    [sheet],
  );
  const showPowerColumns = sheet?.layout === "power";

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8">
      <div className="mb-6 flex items-baseline justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-medium">Excel BOQ Extractor</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Upload a vendor&apos;s priced spreadsheet to pull out a normalized bill of
            quantities. Parsed in memory only, nothing is saved and nothing is written
            to Maximo.
          </p>
        </div>
        <Link href="/" className="text-sm text-primary underline-offset-4 hover:underline">
          Back to projects
        </Link>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging ? "border-primary bg-primary/5" : "border-border/70 hover:bg-muted/40"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xlsm"
          className="hidden"
          onChange={(e) => {
            const picked = e.target.files?.[0];
            if (picked) void handleFile(picked);
            // Reset so re-picking the same file fires onChange again.
            e.target.value = "";
          }}
        />
        <p className="text-sm font-medium">
          {status === "parsing" ? "Parsing..." : "Drop an .xlsx file here, or click to browse"}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {file ? file.name : "Supports the ADDC power template and the water bill template"}
        </p>
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {result && (
        <>
          <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Card size="sm">
              <CardHeader>
                <CardTitle className="text-xs text-muted-foreground">Tender</CardTitle>
              </CardHeader>
              <CardContent className="font-heading text-lg">
                {result.tender_ref ?? "Not found"}
              </CardContent>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardTitle className="text-xs text-muted-foreground">Priced lines</CardTitle>
              </CardHeader>
              <CardContent className="font-heading text-lg">
                {formatNumber(result.item_count)}
              </CardContent>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardTitle className="text-xs text-muted-foreground">Extracted total</CardTitle>
              </CardHeader>
              <CardContent className="font-heading text-lg">
                {money(result.grand_total)}
              </CardContent>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardTitle className="text-xs text-muted-foreground">Vendor stated total</CardTitle>
              </CardHeader>
              <CardContent className="font-heading text-lg">
                {result.stated_total == null ? "Not stated" : money(result.stated_total)}
              </CardContent>
            </Card>
          </div>

          {result.reconciliation && (
            <div
              className={`mt-3 rounded-lg border px-4 py-3 text-sm ${
                result.reconciliation.agrees
                  ? "border-border/60 bg-muted/40"
                  : "border-destructive/40 bg-destructive/10 text-destructive"
              }`}
            >
              {result.reconciliation.agrees ? (
                <>
                  <strong>Reconciles.</strong>{" "}
                  The extracted line items match the vendor&apos;s own stated total to within{" "}
                  {result.reconciliation.percent.toFixed(2)}%.
                </>
              ) : (
                <>
                  <strong>Does not reconcile.</strong>{" "}
                  Extracted lines total{" "}
                  {money(result.reconciliation.extracted_total)}{" "}
                  but the vendor&apos;s summary sheet states{" "}
                  {money(result.reconciliation.stated_total)}, a difference of{" "}
                  {money(Math.abs(result.reconciliation.difference))}{" "}
                  ({result.reconciliation.percent.toFixed(2)}%). Either the extraction missed
                  lines, or the vendor&apos;s own summary disagrees with their priced detail.
                </>
              )}
            </div>
          )}

          {result.arithmetic_error_count > 0 && (
            <div className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
              <strong>{result.arithmetic_error_count}</strong>{" "}
              {result.arithmetic_error_count === 1 ? "line has" : "lines have"}{" "}
              a quantity times rate that does not equal the stated total. Flagged in the table below and
              highlighted in the export.
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center gap-2">
            {result.sheets.map((s, index) => (
              <Button
                key={s.sheet_name}
                size="sm"
                variant={index === activeSheet ? "default" : "outline"}
                onClick={() => setActiveSheet(index)}
              >
                {s.sheet_name}
                <Badge variant={s.role === "summary" ? "secondary" : "outline"} className="ml-1">
                  {s.role === "summary" ? "summary" : `${s.item_count}`}
                </Badge>
              </Button>
            ))}
            <div className="ml-auto">
              <Button onClick={onExport} disabled={status === "exporting"}>
                {status === "exporting" ? "Building..." : "Download normalized BOQ"}
              </Button>
            </div>
          </div>

          {sheet && (
            <Card className="mt-3">
              <CardHeader>
                <CardTitle>
                  {sheet.sheet_name}{" "}
                  <span className="text-sm font-normal text-muted-foreground">
                    {sheet.layout}{" "}
                    layout, header on row {sheet.header_row}, sheet total{" "}
                    {money(sheet.total)}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-left text-xs">
                  <thead className="border-b text-muted-foreground">
                    <tr>
                      <th className="py-2 pr-3 font-medium">Item</th>
                      <th className="py-2 pr-3 font-medium">Description</th>
                      <th className="py-2 pr-3 font-medium">Unit</th>
                      <th className="py-2 pr-3 text-right font-medium">Qty</th>
                      {showPowerColumns ? (
                        <>
                          <th className="py-2 pr-3 text-right font-medium">CIF rate</th>
                          <th className="py-2 pr-3 text-right font-medium">CIF total</th>
                          <th className="py-2 pr-3 text-right font-medium">Erect. rate</th>
                          <th className="py-2 pr-3 text-right font-medium">Erect. total</th>
                        </>
                      ) : (
                        <th className="py-2 pr-3 text-right font-medium">Unit rate</th>
                      )}
                      <th className="py-2 pr-3 text-right font-medium">Line total</th>
                      <th className="py-2 font-medium">Issue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleLines.map((line) => (
                      <tr
                        key={`${sheet.sheet_name}-${line.row_number}`}
                        className={
                          line.kind === "section"
                            ? "border-b bg-muted/50 font-medium"
                            : line.kind === "subtotal"
                              ? "border-b text-muted-foreground italic"
                              : line.issue
                                ? "border-b bg-amber-500/10"
                                : "border-b"
                        }
                      >
                        <td className="py-1.5 pr-3 whitespace-nowrap">{lineLabel(line)}</td>
                        <td className="max-w-[420px] py-1.5 pr-3">
                          <span className="line-clamp-2">{line.description}</span>
                        </td>
                        <td className="py-1.5 pr-3 whitespace-nowrap">{line.unit ?? ""}</td>
                        <td className="py-1.5 pr-3 text-right">{money(line.quantity)}</td>
                        {showPowerColumns ? (
                          <>
                            <td className="py-1.5 pr-3 text-right">{money(line.cif_unit_rate)}</td>
                            <td className="py-1.5 pr-3 text-right">{money(line.cif_total)}</td>
                            <td className="py-1.5 pr-3 text-right">
                              {money(line.erection_unit_rate)}
                            </td>
                            <td className="py-1.5 pr-3 text-right">{money(line.erection_total)}</td>
                          </>
                        ) : (
                          <td className="py-1.5 pr-3 text-right">{money(line.unit_rate)}</td>
                        )}
                        <td className="py-1.5 pr-3 text-right font-medium">
                          {money(line.line_total)}
                        </td>
                        <td className="py-1.5 text-muted-foreground">{line.issue ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {hiddenCount > 0 && (
                  <p className="pt-3 text-xs text-muted-foreground">
                    Showing the first {PREVIEW_LINES} rows.{" "}
                    {formatNumber(hiddenCount)}{" "}
                    more are in the downloadable workbook.
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {result.skipped.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              Skipped sheets:{" "}
              {result.skipped.map((s) => `${s.sheet_name} (${s.reason})`).join(", ")}
            </p>
          )}
        </>
      )}
    </div>
  );
}
