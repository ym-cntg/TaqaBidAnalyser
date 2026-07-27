"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FileText, FileSpreadsheet, File, AlertTriangle, ArrowRight } from "lucide-react";
import {
  getProjectFiles,
  setFileSelection,
  type ProjectFilesResponse,
  type ProjectBidderFiles,
} from "@/lib/api";
import { useCurrentProject } from "@/lib/project-context";

function formatSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(0)} KB`;
  return `${bytes} B`;
}

function fileIcon(ext: string) {
  if (ext === ".xlsx" || ext === ".xls") return FileSpreadsheet;
  if (ext === ".pdf") return FileText;
  return File;
}

export default function DocumentsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { project } = useCurrentProject();
  const [projectFiles, setProjectFiles] = useState<ProjectFilesResponse | null>(null);
  const [pendingPaths, setPendingPaths] = useState<Set<string>>(new Set());
  const [bulkBusyBidders, setBulkBusyBidders] = useState<Set<string>>(new Set());
  const [globalBulkBusy, setGlobalBulkBusy] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    getProjectFiles(projectId).then(setProjectFiles);
  }, [projectId]);

  async function toggleFile(bidder: string, path: string, nextSelected: boolean) {
    const key = `${bidder}::${path}`;
    setPendingPaths((prev) => new Set(prev).add(key));

    // Optimistic update so checkbox feels instant even though the toggle
    // round-trips to disk (selections are persisted, not in-memory-only).
    setProjectFiles((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        bidders: prev.bidders.map((b) =>
          b.bidder !== bidder
            ? b
            : {
                ...b,
                selected_count: b.selected_count + (nextSelected ? 1 : -1),
                files: b.files.map((f) =>
                  f.path !== path ? f : { ...f, selected: nextSelected }
                ),
              }
        ),
      };
    });

    try {
      await setFileSelection(projectId, bidder, path, nextSelected);
    } catch {
      // Revert on failure
      setProjectFiles((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          bidders: prev.bidders.map((b) =>
            b.bidder !== bidder
              ? b
              : {
                  ...b,
                  selected_count: b.selected_count + (nextSelected ? -1 : 1),
                  files: b.files.map((f) =>
                    f.path !== path ? f : { ...f, selected: !nextSelected }
                  ),
                }
          ),
        };
      });
    } finally {
      setPendingPaths((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }

  async function bulkSetForBidder(bidder: ProjectBidderFiles, nextSelected: boolean) {
    setBulkBusyBidders((prev) => new Set(prev).add(bidder.bidder));
    setProjectFiles((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        bidders: prev.bidders.map((b) =>
          b.bidder !== bidder.bidder
            ? b
            : {
                ...b,
                selected_count: nextSelected ? b.files.length : 0,
                files: b.files.map((f) => ({ ...f, selected: nextSelected })),
              }
        ),
      };
    });
    try {
      await Promise.all(
        bidder.files.map((f) => setFileSelection(projectId, bidder.bidder, f.path, nextSelected))
      );
    } catch {
      getProjectFiles(projectId).then(setProjectFiles);
    } finally {
      setBulkBusyBidders((prev) => {
        const next = new Set(prev);
        next.delete(bidder.bidder);
        return next;
      });
    }
  }

  async function bulkSetForProject(nextSelected: boolean) {
    if (!projectFiles) return;
    setGlobalBulkBusy(true);
    const bidders = projectFiles.bidders;
    setProjectFiles((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        bidders: prev.bidders.map((b) => ({
          ...b,
          selected_count: nextSelected ? b.files.length : 0,
          files: b.files.map((f) => ({ ...f, selected: nextSelected })),
        })),
      };
    });
    try {
      await Promise.all(
        bidders.flatMap((b) =>
          b.files.map((f) => setFileSelection(projectId, b.bidder, f.path, nextSelected))
        )
      );
    } catch {
      getProjectFiles(projectId).then(setProjectFiles);
    } finally {
      setGlobalBulkBusy(false);
    }
  }

  const allSelected = !!projectFiles && projectFiles.bidders.every((b) => b.files.every((f) => f.selected));

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Select Bid Documents</h1>
          <p className="text-muted-foreground mt-1">
            Choose which submitted files count as each bidder&apos;s official bid before
            running comparison
          </p>
        </div>
        {projectFiles && (
          <Button
            variant="outline"
            size="sm"
            disabled={globalBulkBusy}
            onClick={() => bulkSetForProject(!allSelected)}
          >
            {allSelected ? "Clear all files" : "Select all files"}
            {globalBulkBusy ? "…" : ""}
          </Button>
        )}
      </div>

      {project && !project.analysis_ready && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-400/40 bg-amber-500/5 px-4 py-3">
          <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 shrink-0" />
          <p className="text-sm text-muted-foreground">
            This project&apos;s BOQ format isn&apos;t wired up to Bid Comparison / BOQ Explorer /
            the rest of Bid Analysis yet. Your selections here are saved either way, so this is
            ready for whenever extraction support is built for this format.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {projectFiles?.bidders.map((bidder) => (
          <Card key={bidder.bidder}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-2 text-base">
                <span className="truncate" title={bidder.bidder}>
                  {bidder.bidder}
                </span>
                <span className="flex items-center gap-2 shrink-0">
                  <Badge
                    className={
                      bidder.selected_count > 0
                        ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                        : ""
                    }
                    variant={bidder.selected_count > 0 ? undefined : "outline"}
                  >
                    {bidder.selected_count} selected
                  </Badge>
                  <Button
                    variant="ghost"
                    size="xs"
                    disabled={bulkBusyBidders.has(bidder.bidder)}
                    onClick={() => bulkSetForBidder(bidder, bidder.selected_count !== bidder.files.length)}
                  >
                    {bidder.selected_count === bidder.files.length ? "Clear all" : "Select all"}
                  </Button>
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {bidder.files.map((file) => {
                const Icon = fileIcon(file.ext);
                const key = `${bidder.bidder}::${file.path}`;
                const pending = pendingPaths.has(key);
                return (
                  <label
                    key={file.path}
                    className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm cursor-pointer transition-colors ${
                      file.selected ? "bg-primary/[0.06]" : "hover:bg-muted/60"
                    } ${pending ? "opacity-60" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={file.selected}
                      disabled={pending}
                      onChange={(e) =>
                        toggleFile(bidder.bidder, file.path, e.target.checked)
                      }
                      className="h-3.5 w-3.5 accent-primary shrink-0"
                    />
                    <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <span
                      className={`flex-1 truncate ${
                        file.selected ? "font-medium" : "text-muted-foreground"
                      }`}
                      title={file.name}
                    >
                      {file.name}
                    </span>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {formatSize(file.size)}
                    </span>
                  </label>
                );
              })}
            </CardContent>
          </Card>
        ))}
      </div>

      {project?.analysis_ready && (
        <div className="flex items-center gap-3 pt-2">
          <Link
            href={`/projects/${projectId}/explorer`}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
          >
            Continue to BOQ Explorer <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}
    </div>
  );
}
