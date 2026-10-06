"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  createProject,
  createUploadProject,
  getProjects,
  getRfqs,
  listUploadProjects,
  type ProjectSummary,
  type RfqSummary,
  type UploadProjectListItem,
} from "@/lib/api";
import { BOQ_CATEGORY_BADGE_VARIANT, BOQ_CATEGORY_LABELS } from "@/lib/boq-category";
import { formatDate } from "@/lib/format";
import { clearCachedIdentity, resolveIdentity, type CachedIdentity } from "@/lib/identity";
import { ORG_OPTIONS } from "@/lib/orgs";

type IdentityState =
  | { status: "resolving" }
  | { status: "needs-name"; error?: string }
  | { status: "error"; error: string }
  | { status: "ready"; identity: CachedIdentity };

// Deliberately no message-rewriting here -- always show the backend's
// actual error text verbatim. An earlier version of this page pattern-
// matched on the word "grant" to show a canned "pending an admin grant"
// banner, but the backend's own error strings happened to contain that
// word too, so real, unrelated errors got silently mislabeled. Never
// hide the real cause behind a guess.

export default function Home() {
  const router = useRouter();
  const [identityState, setIdentityState] = useState<IdentityState>({ status: "resolving" });
  const [nameInput, setNameInput] = useState("");

  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  // Uploaded projects live in their own store, not bid_analyzer_projects,
  // so they are listed separately and merged into the same grid.
  const [uploads, setUploads] = useState<UploadProjectListItem[]>([]);
  const [uploadName, setUploadName] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [mode, setMode] = useState<"maximo" | "upload">("maximo");
  const [listStatus, setListStatus] = useState<"loading" | "ok" | "error">("loading");
  const [listError, setListError] = useState<string | null>(null);

  const [panelOpen, setPanelOpen] = useState(false);

  function tryResolveIdentity(displayName?: string) {
    resolveIdentity(displayName)
      .then((identity) => setIdentityState({ status: "ready", identity }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 400) {
          setIdentityState({ status: "needs-name" });
        } else {
          setIdentityState({
            status: "error",
            error: err instanceof Error ? err.message : String(err),
          });
        }
      });
  }

  // Fail-soft: uploaded projects are a BETA extra, so a failure to
  // list them must not take out the main projects page.
  useEffect(() => {
    listUploadProjects()
      .then((r) => setUploads(r.projects))
      .catch(() => setUploads([]));
  }, []);

  useEffect(() => {
    tryResolveIdentity();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (identityState.status !== "ready") return;
    setListStatus("loading");
    setListError(null);
    getProjects(identityState.identity.userId)
      .then((res) => {
        setProjects(res.projects);
        setListStatus("ok");
      })
      .catch((err) => {
        setListError(err instanceof Error ? err.message : String(err));
        setListStatus("error");
      });
  }, [identityState]);

  function submitName(e: React.FormEvent) {
    e.preventDefault();
    if (!nameInput.trim()) return;
    tryResolveIdentity(nameInput.trim());
  }

  function switchUser() {
    clearCachedIdentity();
    setProjects(null);
    setIdentityState({ status: "resolving" });
    tryResolveIdentity();
  }

  if (identityState.status === "resolving") {
    return (
      <main className="min-h-screen bg-app-gradient">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <p className="text-center py-12 text-muted-foreground animate-pulse">Loading…</p>
        </div>
      </main>
    );
  }

  if (identityState.status === "error") {
    return (
      <main className="min-h-screen bg-app-gradient">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-600">
            {identityState.error}
          </div>
        </div>
      </main>
    );
  }

  if (identityState.status === "needs-name") {
    return (
      <main className="min-h-screen bg-app-gradient">
        <div className="mx-auto max-w-md px-6 py-16">
          <Card>
            <CardHeader>
              <CardTitle>What should we call you?</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={submitName} className="flex flex-col gap-3">
                <input
                  autoFocus
                  type="text"
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  placeholder="Your name"
                  className="h-8 rounded-lg border border-border bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                />
                <Button type="submit">Continue</Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </main>
    );
  }

  const identity = identityState.identity;

  return (
    <main className="min-h-screen bg-app-gradient">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <header className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold">Projects</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Each project tracks the analysis for one RFQ.
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm">{identity.displayName}</p>
            <button
              onClick={switchUser}
              className="text-xs text-muted-foreground underline hover:text-foreground"
            >
              switch user
            </button>
          </div>
        </header>

        <div className="mb-6">
          <Button onClick={() => setPanelOpen((v) => !v)}>{panelOpen ? "Cancel" : "New project"}</Button>
          {panelOpen && (
            <div className="mt-3 rounded-xl border border-border/60 bg-card p-4">
              <p className="mb-2 text-sm font-medium">Where is the pricing coming from?</p>
              <div className="mb-4 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant={mode === "maximo" ? "default" : "outline"}
                  onClick={() => setMode("maximo")}
                >
                  Select an RFQ from Maximo
                </Button>
                <Button
                  size="sm"
                  variant={mode === "upload" ? "default" : "outline"}
                  onClick={() => setMode("upload")}
                >
                  Upload vendor Excel files
                  <Badge variant="secondary" className="ml-1 bg-amber-500/15 text-amber-700">
                    BETA
                  </Badge>
                </Button>
              </div>

              {mode === "maximo" ? (
                <CreateProjectPanel
                  userId={identity.userId}
                  onCreated={(project) => router.push(`/projects/${project.project_id}`)}
                />
              ) : (
                <div className="space-y-3">
                  <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-800">
                    <strong>Under active testing and development.</strong>{" "}
                    Check every extracted figure before confirming, and use the Maximo path for any
                    evaluation that counts. Uploaded BOQs are lost if the app restarts.
                  </div>
                  <div className="flex flex-wrap items-end gap-2">
                    <label className="text-xs">
                      <span className="mb-1 block text-muted-foreground">Project name</span>
                      <input
                        value={uploadName}
                        onChange={(e) => setUploadName(e.target.value)}
                        placeholder="D-111808 Lot 1"
                        className="h-8 w-72 rounded-lg border border-border bg-background px-2 text-sm"
                      />
                    </label>
                    <Button
                      disabled={uploadBusy || !uploadName.trim()}
                      onClick={async () => {
                        setUploadBusy(true);
                        try {
                          const created = await createUploadProject(
                            uploadName.trim(),
                            identity.userId,
                            identity.displayName,
                          );
                          router.push(`/uploads/${created.project_id}`);
                        } catch (err) {
                          setListError(err instanceof Error ? err.message : String(err));
                        } finally {
                          setUploadBusy(false);
                        }
                      }}
                    >
                      {uploadBusy ? "Creating\u2026" : "Create and upload files"}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {listStatus === "loading" && (
          <p className="text-center py-12 text-muted-foreground animate-pulse">Loading projects…</p>
        )}

        {listStatus === "error" && (
          <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-600">
            {listError}
          </div>
        )}

        {listStatus === "ok" && projects && (
          <>
            {uploads.length > 0 && (
              <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {uploads.map((u) => (
                  <Link
                    key={u.project_id}
                    href={u.confirmed ? `/projects/${u.project_id}` : `/uploads/${u.project_id}`}
                  >
                    <Card className="h-full cursor-pointer border-amber-500/40 transition-shadow hover:shadow-md">
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                          {u.name}
                          <Badge variant="secondary" className="bg-amber-500/15 text-amber-700">
                            BETA
                          </Badge>
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-1 text-sm text-muted-foreground">
                        <p>Uploaded Excel · {u.vendor_count} vendor{u.vendor_count === 1 ? "" : "s"} · {u.line_count} lines</p>
                        <p>{u.confirmed ? "Confirmed, analysis ready" : "Draft, needs review and confirming"}</p>
                        <p className="text-xs">{u.created_by_label ?? u.created_by}</p>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            )}

            {projects.length === 0 && uploads.length === 0 ? (
              <p className="text-center py-12 text-muted-foreground">
                No projects yet. Create one to get started.
              </p>
            ) : projects.length === 0 ? null : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {projects.map((p) => (
                  <Link key={p.project_id} href={`/projects/${p.project_id}`}>
                    <Card className="h-full cursor-pointer transition-shadow hover:shadow-md">
                      <CardHeader>
                        <CardTitle>{p.name}</CardTitle>
                      </CardHeader>
                      <CardContent className="flex flex-col gap-2">
                        <p className="font-mono text-xs text-muted-foreground">{p.rfqnum}</p>
                        <p className="truncate text-sm" title={p.rfq_description ?? ""}>
                          {p.rfq_description ?? "—"}
                        </p>
                        <div className="flex flex-wrap items-center gap-2">
                          {p.boq_category && (
                            <Badge variant={BOQ_CATEGORY_BADGE_VARIANT[p.boq_category]}>
                              {BOQ_CATEGORY_LABELS[p.boq_category]}
                            </Badge>
                          )}
                          <span className="text-xs text-muted-foreground">{formatDate(p.created_at)}</span>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}

const RFQ_PICKER_PAGE_SIZE = 20;

function CreateProjectPanel({
  userId,
  onCreated,
}: {
  userId: string;
  onCreated: (project: ProjectSummary) => void;
}) {
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [orgId, setOrgId] = useState("ADDCORG");
  const [selected, setSelected] = useState<RfqSummary | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [results, setResults] = useState<RfqSummary[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [rfqStatus, setRfqStatus] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  // Populated immediately on open (no search needed) so this reads as a
  // browsable list, same as the /rfqs page -- not a blind text field that
  // only reacts once you happen to type something that matches.
  useEffect(() => {
    if (selected) return;
    setRfqStatus("loading");
    getRfqs({ search: debouncedSearch || undefined, orgId, pageSize: RFQ_PICKER_PAGE_SIZE })
      .then((res) => {
        setResults(res.rfqs);
        setTotalCount(res.total_count);
        setRfqStatus("ok");
      })
      .catch(() => setRfqStatus("error"));
  }, [debouncedSearch, orgId, selected]);

  async function submit() {
    if (!name.trim() || !selected) return;
    setSubmitting(true);
    setError(null);
    try {
      const project = await createProject({ name: name.trim(), rfqnum: selected.rfqnum, userId });
      onCreated(project);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="mt-4 max-w-2xl">
      <CardHeader>
        <CardTitle>New project</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Project name"
          className="h-8 rounded-lg border border-border bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />

        {selected ? (
          <div className="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-2.5 py-1.5 text-sm">
            <span className="flex items-center gap-2">
              <span className="font-mono text-xs">{selected.rfqnum}</span>
              <span className="truncate">{selected.description ?? "—"}</span>
              <Badge variant={BOQ_CATEGORY_BADGE_VARIANT[selected.boq_category]}>
                {BOQ_CATEGORY_LABELS[selected.boq_category]}
              </Badge>
            </span>
            <button
              onClick={() => setSelected(null)}
              className="shrink-0 text-xs text-muted-foreground hover:text-foreground"
            >
              change
            </button>
          </div>
        ) : (
          <>
            <div className="flex gap-2">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search RFQ number or description…"
                className="h-8 min-w-0 flex-1 rounded-lg border border-border bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
              <select
                value={orgId}
                onChange={(e) => setOrgId(e.target.value)}
                className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
              >
                {ORG_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>

            {rfqStatus === "loading" && (
              <p className="py-4 text-center text-sm text-muted-foreground animate-pulse">Loading RFQs…</p>
            )}
            {rfqStatus === "error" && (
              <p className="py-4 text-center text-sm text-red-600">Could not load RFQs.</p>
            )}
            {rfqStatus === "ok" && results.length === 0 && (
              <p className="py-4 text-center text-sm text-muted-foreground">No RFQs match.</p>
            )}
            {rfqStatus === "ok" && results.length > 0 && (
              <div className="max-h-64 overflow-y-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <tbody>
                    {results.map((r) => (
                      <tr
                        key={r.rfqnum}
                        onClick={() => {
                          setSelected(r);
                          setSearch("");
                        }}
                        className="cursor-pointer border-b border-border/40 odd:bg-muted/[0.15] last:border-0 hover:bg-muted"
                      >
                        <td className="whitespace-nowrap px-2.5 py-1.5 font-mono text-xs">{r.rfqnum}</td>
                        <td className="max-w-[260px] truncate px-2.5 py-1.5" title={r.description ?? ""}>
                          {r.description ?? "—"}
                        </td>
                        <td className="whitespace-nowrap px-2.5 py-1.5">
                          <Badge variant={BOQ_CATEGORY_BADGE_VARIANT[r.boq_category]}>
                            {BOQ_CATEGORY_LABELS[r.boq_category]}
                          </Badge>
                        </td>
                        <td className="whitespace-nowrap px-2.5 py-1.5 text-right text-xs text-muted-foreground">
                          {r.vendor_count} vendors
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {rfqStatus === "ok" && totalCount > results.length && (
              <p className="text-xs text-muted-foreground">
                Showing {results.length} of {totalCount.toLocaleString()} — narrow your search to find more.
              </p>
            )}
          </>
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}

        <Button onClick={submit} disabled={!name.trim() || !selected || submitting}>
          {submitting ? "Creating…" : "Create"}
        </Button>
      </CardContent>
    </Card>
  );
}
