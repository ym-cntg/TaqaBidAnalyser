"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Plus, Zap, Trash2, FolderOpen, CheckCircle2, LogOut } from "lucide-react";
import {
  getProjects,
  createProject,
  deleteProject,
  getDiscoverableRoots,
  type Project,
} from "@/lib/api";
import { getIdentity, clearIdentity, type Identity } from "@/lib/auth";

export default function ProjectsPage() {
  const router = useRouter();
  const [identity, setIdentityState] = useState<Identity | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [roots, setRoots] = useState<string[]>([]);
  const [form, setForm] = useState({ name: "", tender_no: "", description: "", root: "" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    getProjects()
      .then(setProjects)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    setIdentityState(getIdentity());
    refresh();
  }, []);

  function openCreate() {
    setCreateError(null);
    setForm({ name: "", tender_no: "", description: "", root: "" });
    getDiscoverableRoots().then(setRoots);
    setCreateOpen(true);
  }

  async function handleCreate() {
    if (!form.name.trim() || !form.root.trim()) {
      setCreateError("Name and a data folder are both required");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const project = await createProject({
        ...form,
        created_by: identity?.name ?? "",
      });
      setCreateOpen(false);
      setProjects((prev) => [...prev, project]);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Failed to create project");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Remove this project? Its data folder is untouched — only the project record is deleted.")) {
      return;
    }
    await deleteProject(id);
    setProjects((prev) => prev.filter((p) => p.id !== id));
  }

  function handleLogout() {
    clearIdentity();
    router.push("/login");
  }

  return (
    <div className="min-h-screen bg-app-gradient">
      <header className="border-b border-border/60 bg-card">
        <div className="max-w-5xl mx-auto px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-[oklch(0.62_0.15_190)]">
              <Zap className="h-4 w-4 text-primary-foreground" fill="currentColor" />
            </div>
            <span className="font-semibold tracking-tight">TAQA Bid Analyzer</span>
          </div>
          <div className="flex items-center gap-3">
            {identity && <span className="text-sm text-muted-foreground">{identity.name}</span>}
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="h-3.5 w-3.5" /> Log out
            </Button>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-8 py-8 space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
            <p className="text-muted-foreground mt-1">
              Pick a bid to work on, or start a new one
            </p>
          </div>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" /> New Project
          </Button>
        </div>

        {loading ? (
          <div className="text-center py-12 text-muted-foreground animate-pulse">Loading projects...</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.map((p) => (
              <Card key={p.id}>
                <CardHeader>
                  <CardTitle className="flex items-start justify-between gap-2">
                    <span className="truncate" title={p.name}>
                      {p.name}
                    </span>
                    <button
                      onClick={() => handleDelete(p.id)}
                      className="text-muted-foreground hover:text-destructive shrink-0"
                      title="Remove project record (data folder untouched)"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {p.description || "No description"}
                  </p>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline">{p.tender_no}</Badge>
                    {p.analysis_ready ? (
                      <Badge className="bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="h-3 w-3" /> Analysis ready
                      </Badge>
                    ) : (
                      <Badge variant="secondary">Curation only</Badge>
                    )}
                    {!p.exists && (
                      <Badge variant="destructive">Data folder missing</Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span>{p.bidder_count} bidders</span>
                    <span>{p.file_count} files</span>
                    <span>{p.selected_count} selected</span>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={() => router.push(`/projects/${p.id}/documents`)}
                  >
                    <FolderOpen className="h-3.5 w-3.5" /> Open
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New project</DialogTitle>
            <DialogDescription>
              Point it at a bidder-data folder under <span className="font-mono">data/</span> —
              document selection works for any shape; full analysis only runs for BOQ formats the
              extraction pipeline already understands.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. B-24501 — New Substation Bid"
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Tender No.</label>
              <input
                type="text"
                value={form.tender_no}
                onChange={(e) => setForm((f) => ({ ...f, tender_no: e.target.value }))}
                placeholder="e.g. B-24501"
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Description</label>
              <input
                type="text"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Data folder (under data/)
              </label>
              {roots.length > 0 && (
                <select
                  value={roots.includes(form.root) ? form.root : ""}
                  onChange={(e) => setForm((f) => ({ ...f, root: e.target.value }))}
                  className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="">Select a discovered folder...</option>
                  {roots.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              )}
              <input
                type="text"
                value={form.root}
                onChange={(e) => setForm((f) => ({ ...f, root: e.target.value }))}
                placeholder="or type a relative path, e.g. new-tender"
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
              />
              <p className="text-xs text-muted-foreground mt-1">
                {roots.length > 0
                  ? "Pick a discovered folder above, or type any relative path under data/ manually."
                  : "No unclaimed folders were discovered under data/ — type a relative path manually."}
              </p>
            </div>
            {createError && (
              <p className="text-sm text-destructive">{createError}</p>
            )}
          </div>

          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            <Button disabled={creating} onClick={handleCreate}>
              Create project{creating ? "…" : ""}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
