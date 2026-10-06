"use client";

import { Check, Pencil, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  ORIGINAL_ROUND,
  addUploadFile,
  confirmUploadProject,
  deleteUploadLine,
  editUploadLine,
  editUploadPrice,
  getUploadProject,
  removeUploadFile,
  reopenUploadProject,
  type UploadProject,
} from "@/lib/api";
import { formatAED, formatNumber } from "@/lib/format";
import { BetaBadge, BetaNotice } from "./beta-notice";

const PREVIEW_LINES = 250;

function roundLabel(r: string): string {
  return r === ORIGINAL_ROUND ? "Original" : `Round ${Number(r)}`;
}

export function UploadWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [project, setProject] = useState<UploadProject | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [vendor, setVendor] = useState("");
  const [vendorName, setVendorName] = useState("");
  const [round, setRound] = useState(ORIGINAL_ROUND);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<{ description: string; quantity: string; unit: string }>({
    description: "",
    quantity: "",
    unit: "",
  });
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getUploadProject(projectId)
      .then((p) => {
        setProject(p);
        setStatus("ok");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
  }, [projectId]);

  const run = useCallback(async (fn: () => Promise<UploadProject>) => {
    setBusy(true);
    setError(null);
    try {
      setProject(await fn());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);

  function onPick(file: File) {
    if (!vendor.trim()) {
      setError("Enter the vendor this file belongs to before uploading it.");
      return;
    }
    void run(() => addUploadFile(projectId, file, vendor.trim(), round, vendorName.trim() || undefined));
  }

  function startEdit(lineNumber: number, description: string, quantity: number | null, unit: string | null) {
    setEditing(lineNumber);
    setDraft({ description, quantity: quantity == null ? "" : String(quantity), unit: unit ?? "" });
  }

  function saveEdit(lineNumber: number) {
    const patch: { description?: string; quantity?: number; unit?: string } = {
      description: draft.description,
      unit: draft.unit,
    };
    const q = Number(draft.quantity);
    if (draft.quantity.trim() !== "" && Number.isFinite(q) && q > 0) patch.quantity = q;
    setEditing(null);
    void run(() => editUploadLine(projectId, lineNumber, patch));
  }

  if (status === "loading") {
    return <main className="min-h-screen bg-app-gradient"><p className="py-16 text-center text-muted-foreground animate-pulse">Loading…</p></main>;
  }
  if (status === "error" || !project) {
    return (
      <main className="min-h-screen bg-app-gradient">
        <div className="mx-auto max-w-3xl px-6 py-10 space-y-3">
          <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">← Projects</Link>
          <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-600">{error}</div>
        </div>
      </main>
    );
  }

  const columns = project.vendors.flatMap((v) => project.rounds.map((r) => ({ vendor: v.vendor, round: r })));
  const visible = project.lines.slice(0, PREVIEW_LINES);
  const hidden = project.lines.length - visible.length;

  return (
    <main className="min-h-screen bg-app-gradient">
      <div className="mx-auto max-w-[1600px] px-6 py-6 space-y-4">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">← Projects</Link>

        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold">
              {project.name} <BetaBadge />
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Excel upload project ·{" "}
              {formatNumber(project.line_count)} lines ·{" "}
              {project.vendors.length} vendor{project.vendors.length === 1 ? "" : "s"} ·{" "}
              {project.rounds.length} round{project.rounds.length === 1 ? "" : "s"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {project.confirmed ? (
              <>
                <Button variant="outline" onClick={() => void run(() => reopenUploadProject(projectId))} disabled={busy}>
                  Reopen for editing
                </Button>
                <Button onClick={() => router.push(`/projects/${projectId}`)}>
                  Open analysis
                </Button>
              </>
            ) : (
              <Button
                onClick={() =>
                  void run(async () => {
                    const p = await confirmUploadProject(projectId);
                    router.push(`/projects/${projectId}`);
                    return p;
                  })
                }
                disabled={busy || project.line_count === 0 || project.vendors.length === 0}
              >
                <Check className="h-4 w-4" /> Confirm and open analysis
              </Button>
            )}
          </div>
        </div>

        <BetaNotice />

        {error && (
          <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-3 text-sm text-red-600">{error}</div>
        )}

        {project.confirmed && (
          <div className="rounded-lg border border-border/60 bg-muted/40 px-4 py-3 text-sm">
            This BOQ is confirmed and in use by the analysis tabs. Reopen it to make further edits.
          </div>
        )}

        {!project.confirmed && (
          <div className="rounded-xl border border-border/60 bg-card p-4 space-y-3">
            <h2 className="text-sm font-semibold">Add a vendor&apos;s priced BOQ</h2>
            <p className="text-xs text-muted-foreground">
              One file per vendor per round. Upload each vendor&apos;s original submission first, then
              any later rounds. Lines are matched across files by BOQ item number.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-xs">
                <span className="mb-1 block text-muted-foreground">Vendor code</span>
                <input
                  value={vendor}
                  onChange={(e) => setVendor(e.target.value)}
                  placeholder="AGPOWER"
                  className="h-8 w-40 rounded-lg border border-border bg-background px-2 text-sm"
                />
              </label>
              <label className="text-xs">
                <span className="mb-1 block text-muted-foreground">Display name (optional)</span>
                <input
                  value={vendorName}
                  onChange={(e) => setVendorName(e.target.value)}
                  placeholder="AG Power Contracting"
                  className="h-8 w-56 rounded-lg border border-border bg-background px-2 text-sm"
                />
              </label>
              <label className="text-xs">
                <span className="mb-1 block text-muted-foreground">Round</span>
                <select
                  value={round}
                  onChange={(e) => setRound(e.target.value)}
                  className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
                >
                  <option value={ORIGINAL_ROUND}>Original</option>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={String(n)}>Round {n}</option>
                  ))}
                </select>
              </label>
              <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={busy}>
                <Upload className="h-4 w-4" /> {busy ? "Working…" : "Choose .xlsx"}
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.xlsm"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onPick(f);
                  e.target.value = "";
                }}
              />
            </div>
          </div>
        )}

        {project.submissions.length > 0 && (
          <div className="rounded-xl border border-border/60 bg-card p-4">
            <h2 className="mb-2 text-sm font-semibold">Uploaded files</h2>
            <table className="w-full text-xs">
              <thead className="border-b text-muted-foreground">
                <tr>
                  <th className="py-1.5 pr-3 text-left font-medium">Vendor</th>
                  <th className="py-1.5 pr-3 text-left font-medium">Round</th>
                  <th className="py-1.5 pr-3 text-left font-medium">File</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Lines</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Extracted total</th>
                  <th className="py-1.5 pr-3 text-left font-medium">Cross-check</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {project.submissions.map((s) => (
                  <tr key={s.submission_id} className="border-b last:border-0">
                    <td className="py-1.5 pr-3 font-medium">{s.vendor}</td>
                    <td className="py-1.5 pr-3">{roundLabel(s.round_label)}</td>
                    <td className="py-1.5 pr-3 text-muted-foreground">{s.filename}</td>
                    <td className="py-1.5 pr-3 text-right">{formatNumber(s.line_count)}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{formatAED(s.extracted_total)}</td>
                    <td className="py-1.5 pr-3">
                      {s.reconciles === null ? (
                        <span className="text-muted-foreground">No summary sheet</span>
                      ) : s.reconciles ? (
                        <span className="text-green-700">Matches vendor total</span>
                      ) : (
                        <span className="text-red-600">
                          Differs from vendor total ({formatAED(s.stated_total)})
                        </span>
                      )}
                    </td>
                    <td className="py-1.5 text-right">
                      {!project.confirmed && (
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={() => void run(() => removeUploadFile(projectId, s.submission_id))}
                          disabled={busy}
                        >
                          <Trash2 className="h-3 w-3" /> Remove
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {project.lines.length > 0 && (
          <div className="rounded-xl border border-border/60 bg-card">
            <div className="border-b px-4 py-3">
              <h2 className="text-sm font-semibold">Review the extracted BOQ</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Check the descriptions, quantities and prices before confirming. Everything here is
                editable until you confirm.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-xs">
                <thead className="border-b bg-muted/40 text-muted-foreground">
                  <tr>
                    <th className="px-2 py-2 text-left font-medium">Item</th>
                    <th className="px-2 py-2 text-left font-medium">Description</th>
                    <th className="px-2 py-2 text-left font-medium">Unit</th>
                    <th className="px-2 py-2 text-right font-medium">Qty</th>
                    {columns.map((c) => (
                      <th key={`${c.vendor}|${c.round}`} className="px-2 py-2 text-right font-medium whitespace-nowrap">
                        {c.vendor}
                        <span className="block text-[10px] font-normal opacity-70">{roundLabel(c.round)}</span>
                      </th>
                    ))}
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((line) => {
                    const isEditing = editing === line.line_number;
                    return (
                      <tr key={line.line_number} className="border-b last:border-0">
                        <td className="px-2 py-1.5 whitespace-nowrap">{line.item_no ?? ""}</td>
                        <td className="max-w-[360px] px-2 py-1.5">
                          {isEditing ? (
                            <input
                              value={draft.description}
                              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                              className="h-7 w-full rounded border border-border bg-background px-1.5"
                            />
                          ) : (
                            <span className="line-clamp-2">{line.description}</span>
                          )}
                        </td>
                        <td className="px-2 py-1.5">
                          {isEditing ? (
                            <input
                              value={draft.unit}
                              onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
                              className="h-7 w-16 rounded border border-border bg-background px-1.5"
                            />
                          ) : (
                            line.unit ?? ""
                          )}
                        </td>
                        <td className="px-2 py-1.5 text-right">
                          {isEditing ? (
                            <input
                              value={draft.quantity}
                              onChange={(e) => setDraft({ ...draft, quantity: e.target.value })}
                              className="h-7 w-20 rounded border border-border bg-background px-1.5 text-right"
                            />
                          ) : (
                            formatNumber(line.quantity)
                          )}
                        </td>
                        {columns.map((col) => {
                          const p = line.prices[`${col.vendor}|${col.round}`];
                          return (
                            <td key={`${col.vendor}|${col.round}`} className="px-2 py-1.5 text-right font-mono whitespace-nowrap">
                              {p?.line_cost == null ? (
                                <span className="text-muted-foreground/50">—</span>
                              ) : (
                                formatNumber(p.line_cost)
                              )}
                            </td>
                          );
                        })}
                        <td className="px-2 py-1.5 text-right whitespace-nowrap">
                          {project.confirmed ? null : isEditing ? (
                            <Button size="xs" onClick={() => saveEdit(line.line_number)} disabled={busy}>
                              Save
                            </Button>
                          ) : (
                            <span className="inline-flex gap-1">
                              <Button
                                variant="ghost"
                                size="icon-xs"
                                title="Edit this line"
                                onClick={() => startEdit(line.line_number, line.description, line.quantity, line.unit)}
                              >
                                <Pencil className="h-3 w-3" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon-xs"
                                title="Delete this line"
                                onClick={() => void run(() => deleteUploadLine(projectId, line.line_number))}
                                disabled={busy}
                              >
                                <Trash2 className="h-3 w-3" />
                              </Button>
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {hidden > 0 && (
              <p className="px-4 py-3 text-xs text-muted-foreground">
                Showing the first {formatNumber(PREVIEW_LINES)} of {formatNumber(project.lines.length)} lines.
                All of them are included in the analysis.
              </p>
            )}
          </div>
        )}

        {project.lines.length === 0 && (
          <p className="rounded-xl border border-dashed border-border/70 px-4 py-10 text-center text-sm text-muted-foreground">
            No files uploaded yet. Add each vendor&apos;s priced BOQ above to get started.
          </p>
        )}
      </div>
    </main>
  );
}
