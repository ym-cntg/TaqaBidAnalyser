"use client";

import { useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Upload, FileUp, CheckCircle2, X } from "lucide-react";
import { uploadFile, type UploadResult, type BOQItem } from "@/lib/api";

function formatAED(val: number | null | undefined): string {
  if (val == null) return "-";
  return new Intl.NumberFormat("en-AE", {
    style: "decimal",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

export default function UploadPage() {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeSheet, setActiveSheet] = useState(0);

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setResult(null);
    setUploading(true);
    try {
      const res = await uploadFile(file, "", "uploaded");
      setResult(res);
      setActiveSheet(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div className="p-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Upload & Extract
        </h1>
        <p className="text-muted-foreground mt-1">
          Upload a BOQ file (Excel or PDF) and instantly extract structured bid
          data
        </p>
      </div>

      {/* Drop Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`relative rounded-2xl border-2 border-dashed p-16 text-center transition-all ${
          dragging
            ? "border-primary bg-primary/5 shadow-md shadow-primary/10"
            : "border-border bg-card/50 hover:border-primary/40 hover:bg-primary/[0.02]"
        }`}
      >
        <input
          type="file"
          accept=".xlsx,.pdf"
          onChange={handleFileInput}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        />
        <div className="flex flex-col items-center gap-4">
          {uploading ? (
            <div className="animate-spin h-12 w-12 rounded-full border-4 border-primary border-t-transparent" />
          ) : (
            <div className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center">
              <FileUp className="h-8 w-8 text-primary" />
            </div>
          )}
          <div>
            <p className="text-lg font-medium">
              {uploading ? "Extracting..." : "Drop your BOQ file here"}
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              {uploading
                ? "Scanned PDFs may take 2-3 minutes for OCR processing"
                : "Supports .xlsx and .pdf files"}
            </p>
          </div>
          {!uploading && (
            <Button variant="outline" className="mt-2">
              <Upload className="h-4 w-4 mr-2" />
              Browse Files
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/[0.06] p-4 flex items-center gap-3 shadow-sm">
          <X className="h-5 w-5 text-destructive shrink-0" />
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* Extraction Results */}
      {result && (
        <div className="space-y-6">
          {/* Summary */}
          <div className="flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/[0.06] px-4 py-3 shadow-sm">
            <CheckCircle2 className="h-6 w-6 text-emerald-600 shrink-0" />
            <div>
              <p className="font-semibold">Extraction Complete</p>
              <p className="text-sm text-muted-foreground">
                {result.filename}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <Card>
              <CardContent className="pt-4">
                <p className="text-xs text-muted-foreground">Lot</p>
                <p className="text-sm font-medium mt-1">
                  {result.summary.lot_name}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-xs text-muted-foreground">Line Items</p>
                <p className="text-xl font-bold mt-1">
                  {result.summary.total_items}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-xs text-muted-foreground">CIF Total</p>
                <p className="text-sm font-mono font-medium mt-1">
                  {formatAED(result.summary.total_cif)}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-xs text-muted-foreground">Erection Total</p>
                <p className="text-sm font-mono font-medium mt-1">
                  {formatAED(result.summary.total_erection)}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-xs text-muted-foreground">Total Price</p>
                <p className="text-sm font-mono font-bold mt-1">
                  {formatAED(result.summary.total_price)}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Sheet Tabs */}
          <div className="flex gap-2 border-b border-border pb-0">
            {result.lot.sheets.map((sheet, idx) => (
              <button
                key={sheet.name}
                onClick={() => setActiveSheet(idx)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
                  activeSheet === idx
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                {sheet.name}
                <Badge variant="secondary" className="ml-2 text-xs">
                  {sheet.item_count}
                </Badge>
              </button>
            ))}
          </div>

          {/* Items Table */}
          {result.lot.sheets[activeSheet] && (
            <div className="rounded-xl border border-border/60 shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/60 border-b border-border/60">
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground w-20">
                        Item
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Description
                      </th>
                      <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground w-16">
                        Unit
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-16">
                        Qty
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-28">
                        CIF Rate
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-28">
                        CIF Total
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-28">
                        Erection
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-28">
                        Total (A+B)
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.lot.sheets[activeSheet].items.map(
                      (item: BOQItem, idx: number) => (
                        <tr
                          key={idx}
                          className={`border-t border-border/60 transition-colors ${
                            item.is_section_header
                              ? "bg-primary/[0.05] font-semibold"
                              : "odd:bg-muted/[0.15] hover:bg-primary/[0.04]"
                          }`}
                        >
                          <td className="px-4 py-2 font-mono text-xs">
                            {item.item_no}
                          </td>
                          <td
                            className={`px-4 py-2 ${
                              item.is_section_header
                                ? "font-semibold"
                                : "text-muted-foreground"
                            }`}
                            style={{ maxWidth: 400 }}
                          >
                            <span className="line-clamp-2">
                              {item.description}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-center text-xs">
                            {item.unit}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-xs">
                            {item.qty}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-xs">
                            {formatAED(item.cif_unit_rate)}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-xs">
                            {formatAED(item.cif_total)}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-xs">
                            {formatAED(item.erection_total)}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-xs font-medium">
                            {formatAED(item.total)}
                          </td>
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
