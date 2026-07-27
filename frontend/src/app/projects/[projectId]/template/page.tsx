"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ChevronDown,
  ChevronRight,
  Database,
  FileCheck2,
  Lock,
  Send,
  Sparkles,
} from "lucide-react";
import {
  getWorkflowStatus,
  getTemplate,
  pullRequisition,
  buildTemplate,
  editTemplateRow,
  lockTemplate,
  unlockTemplate,
  issueTemplate,
  resetWorkflow,
  type WorkflowStatus,
  type BoqTemplate,
  type WorkflowStage,
} from "@/lib/api";
import { useCurrentProject } from "@/lib/project-context";
import { AnalysisNotAvailable } from "@/components/analysis-not-available";
import { getIdentity } from "@/lib/auth";

// Each label names the step to complete while it's the active stage, so
// the stepper reads as "what happens here" rather than a raw status enum
// (e.g. seeing "Pull Requisition" highlighted means "you're on this step",
// not "nothing has happened yet").
const STAGE_LABELS: Record<WorkflowStage, string> = {
  not_started: "Pull Requisition",
  requisition_pulled: "Build Template",
  template_built: "Review & Lock",
  template_locked: "Issue to Market",
  issued: "Issued",
  closed: "Closed",
};

const STAGE_ORDER: WorkflowStage[] = [
  "not_started",
  "requisition_pulled",
  "template_built",
  "template_locked",
  "issued",
];

export default function TemplateBuilderPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { project, loading: projectLoading } = useCurrentProject();
  const [status, setStatus] = useState<WorkflowStatus | null>(null);
  const [template, setTemplate] = useState<BoqTemplate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lockedByInput, setLockedByInput] = useState(() => getIdentity()?.name ?? "");
  const [expandedLots, setExpandedLots] = useState<Set<number>>(new Set());

  async function refreshStatus(id: string) {
    const s = await getWorkflowStatus(id);
    setStatus(s);
    return s;
  }

  useEffect(() => {
    if (!project?.analysis_ready) return;
    setTemplate(null);
    setError(null);
    refreshStatus(projectId).then((s) => {
      if (s.has_template) {
        getTemplate(projectId).then((r) => setTemplate(r.template));
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, project?.analysis_ready]);

  async function run<T>(action: () => Promise<T>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refreshStatus(projectId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function handleBuildTemplate() {
    setBusy(true);
    setError(null);
    try {
      const res = await buildTemplate(projectId);
      setTemplate(res.template);
      await refreshStatus(projectId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  function toggleLot(lotNumber: number) {
    setExpandedLots((prev) => {
      const next = new Set(prev);
      if (next.has(lotNumber)) next.delete(lotNumber);
      else next.add(lotNumber);
      return next;
    });
  }

  async function handleEditRow(
    lotNumber: number,
    sheetName: string,
    itemNo: string,
    field: "description" | "unit" | "qty",
    value: string
  ) {
    const fields = field === "qty" ? { qty: value === "" ? null : Number(value) } : { [field]: value };
    try {
      const res = await editTemplateRow(projectId, lotNumber, sheetName, itemNo, fields);
      setTemplate(res.template);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Edit failed");
    }
  }

  const stage = status?.stage ?? "not_started";
  const canEdit = stage === "template_built";

  if (projectLoading) return null;
  if (!project?.analysis_ready) return <AnalysisNotAvailable project={project} />;

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">BOQ Template Builder</h1>
          <p className="text-muted-foreground mt-1">
            Pull the requisition, build the standardized BOQ template, review &amp; lock it,
            then issue it for the market request
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={busy || stage === "not_started"}
          onClick={() => run(() => resetWorkflow(projectId))}
        >
          Reset (demo)
        </Button>
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-muted/20 px-4 py-3 overflow-x-auto">
        {STAGE_ORDER.map((s, i) => {
          const currentIdx = STAGE_ORDER.indexOf(stage as WorkflowStage);
          const isDone = i < currentIdx || stage === "closed";
          const isCurrent = s === stage;
          return (
            <div key={s} className="flex items-center gap-2 shrink-0">
              <span
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
                  isCurrent
                    ? "bg-primary text-primary-foreground"
                    : isDone
                    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {STAGE_LABELS[s]}
              </span>
              {i < STAGE_ORDER.length - 1 && (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              )}
            </div>
          );
        })}
      </div>

      {error && (
        <div className="rounded-lg border border-red-400/40 bg-red-500/5 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Stage 0: not started */}
      {stage === "not_started" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-4 w-4 text-primary" />
              Pull requisition from Maximo
              <Badge variant="secondary" className="ml-1 text-xs">Simulated integration</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              This demo has no live Maximo connection — clicking below returns a canned
              purchase-requisition payload shaped like a real Maximo export, standing in for the
              integration until credentials/sandbox access exist.
            </p>
            <Button disabled={busy} onClick={() => run(() => pullRequisition(projectId))}>
              Pull requisition{busy ? "…" : ""}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Stage 1: requisition pulled */}
      {stage === "requisition_pulled" && status?.requisition && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {status.requisition.pr_number} — {status.requisition.title}
              <Badge variant="secondary" className="ml-1 text-xs">Simulated</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Requested by {status.requisition.requested_by} · {status.requisition.department}
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {status.requisition.categories.map((c) => (
                <div key={c.category} className="rounded-lg border border-border/60 px-3 py-2 text-sm">
                  <p className="font-medium">{c.category}</p>
                  <p className="text-muted-foreground text-xs mt-0.5">{c.note} · {c.lots} lot(s)</p>
                </div>
              ))}
            </div>
            <Button disabled={busy} onClick={handleBuildTemplate}>
              Build BOQ template{busy ? "…" : ""}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Stage 2+: template built / locked / issued */}
      {(stage === "template_built" || stage === "template_locked" || stage === "issued") && (
        <div className="space-y-4">
          {stage === "template_locked" && (
            <Card className="border-amber-400/40 bg-amber-500/[0.05]">
              <CardContent className="pt-4 flex items-center justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-2 text-sm">
                  <Lock className="h-4 w-4 text-amber-600" />
                  Locked by <span className="font-medium">{status?.locked_by}</span> at{" "}
                  {status?.locked_at ? new Date(status.locked_at).toLocaleString() : ""}
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" disabled={busy} onClick={() => run(() => unlockTemplate(projectId))}>
                    Unlock
                  </Button>
                  <Button size="sm" disabled={busy} onClick={() => run(() => issueTemplate(projectId))}>
                    <Send className="h-3.5 w-3.5" /> Issue for market request
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {stage === "issued" && (
            <Card className="border-emerald-500/40 bg-emerald-500/[0.06]">
              <CardContent className="pt-4 flex items-center gap-3">
                <FileCheck2 className="h-5 w-5 text-emerald-600 shrink-0" />
                <div className="text-sm">
                  <p className="font-medium">Issued to market</p>
                  <p className="text-muted-foreground text-xs mt-0.5">
                    Simulated Maximo reference <span className="font-mono">{status?.maximo_reference}</span> ·{" "}
                    {status?.issued_at ? new Date(status.issued_at).toLocaleString() : ""}
                  </p>
                </div>
                <Badge variant="secondary" className="ml-auto text-xs">Simulated</Badge>
              </CardContent>
            </Card>
          )}

          {stage === "template_built" && (
            <Card>
              <CardContent className="pt-4 flex items-center justify-between gap-4 flex-wrap">
                <p className="text-sm text-muted-foreground">
                  Built from <span className="font-medium text-foreground">{template?.reference_bidder ?? "reference bidder"}</span>'s
                  real submitted item structure — pricing stripped, ready for review.
                </p>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder="Locked by (your name)"
                    value={lockedByInput}
                    onChange={(e) => setLockedByInput(e.target.value)}
                    className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm"
                  />
                  <Button
                    disabled={busy || !lockedByInput.trim()}
                    onClick={() => run(() => lockTemplate(projectId, lockedByInput.trim()))}
                  >
                    <Lock className="h-3.5 w-3.5" /> Lock template
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {template && (
            <div className="space-y-3">
              {template.lots.map((lot) => {
                const isExpanded = expandedLots.has(lot.lot_number);
                const totalItems = lot.sheets.reduce(
                  (sum, s) => sum + s.items.filter((i) => !i.is_section_header).length,
                  0
                );
                return (
                  <Card key={lot.lot_number}>
                    <CardHeader
                      className="cursor-pointer"
                      onClick={() => toggleLot(lot.lot_number)}
                    >
                      <CardTitle className="flex items-center gap-2 text-sm">
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4 text-primary" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-primary" />
                        )}
                        {lot.lot_name}
                        <Badge variant="secondary" className="ml-auto text-xs">
                          {totalItems} items
                        </Badge>
                      </CardTitle>
                    </CardHeader>
                    {isExpanded && (
                      <CardContent className="space-y-4">
                        {lot.sheets.map((sheet) => (
                          <div key={sheet.name} className="overflow-x-auto rounded-lg border border-border/60">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="bg-muted/60 border-b border-border/60">
                                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground w-24">Item</th>
                                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Description</th>
                                  <th className="px-3 py-2 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground w-20">Unit</th>
                                  <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground w-20">Qty</th>
                                </tr>
                              </thead>
                              <tbody>
                                {sheet.items.map((row, idx) => (
                                  <tr
                                    key={`${sheet.name}-${row.item_no}-${idx}`}
                                    className={`border-t border-border/60 ${row.is_section_header ? "bg-primary/[0.04] font-medium" : "odd:bg-muted/[0.1]"}`}
                                  >
                                    <td className="px-3 py-1.5 font-mono text-xs">{row.item_no}</td>
                                    <td className="px-3 py-1.5">
                                      {canEdit && !row.is_section_header ? (
                                        <input
                                          defaultValue={row.description}
                                          onBlur={(e) =>
                                            e.target.value !== row.description &&
                                            handleEditRow(lot.lot_number, sheet.name, row.item_no, "description", e.target.value)
                                          }
                                          className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 hover:border-input focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/50"
                                        />
                                      ) : (
                                        row.description
                                      )}
                                    </td>
                                    <td className="px-3 py-1.5 text-center text-xs">
                                      {canEdit && !row.is_section_header ? (
                                        <input
                                          defaultValue={row.unit ?? ""}
                                          onBlur={(e) =>
                                            e.target.value !== (row.unit ?? "") &&
                                            handleEditRow(lot.lot_number, sheet.name, row.item_no, "unit", e.target.value)
                                          }
                                          className="w-16 rounded border border-transparent bg-transparent px-1 py-0.5 text-center hover:border-input focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/50"
                                        />
                                      ) : (
                                        row.unit
                                      )}
                                    </td>
                                    <td className="px-3 py-1.5 text-right font-mono text-xs">
                                      {canEdit && !row.is_section_header ? (
                                        <input
                                          defaultValue={row.qty ?? ""}
                                          onBlur={(e) =>
                                            Number(e.target.value || 0) !== (row.qty ?? 0) &&
                                            handleEditRow(lot.lot_number, sheet.name, row.item_no, "qty", e.target.value)
                                          }
                                          className="w-16 rounded border border-transparent bg-transparent px-1 py-0.5 text-right font-mono hover:border-input focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/50"
                                        />
                                      ) : (
                                        row.qty
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ))}
                      </CardContent>
                    )}
                  </Card>
                );
              })}
            </div>
          )}

          {!template && (
            <p className="text-sm text-muted-foreground flex items-center gap-2">
              <Sparkles className="h-4 w-4" /> Loading template…
            </p>
          )}
        </div>
      )}
    </div>
  );
}
