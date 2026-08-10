"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { getRfqs, type BoqCategory, type RfqListResponse } from "@/lib/api";
import { BOQ_CATEGORY_BADGE_VARIANT, BOQ_CATEGORY_LABELS, BOQ_CATEGORY_ORDER } from "@/lib/boq-category";
import { formatAED, formatDate } from "@/lib/format";
import { ORG_OPTIONS } from "@/lib/orgs";

const PAGE_SIZE = 50;

export default function Home() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [orgId, setOrgId] = useState("ADDCORG");
  const [boqCategory, setBoqCategory] = useState<BoqCategory | "">("");
  const [page, setPage] = useState(1);

  const [data, setData] = useState<RfqListResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  // Debounce the search box -- avoid firing a request on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    setStatus("loading");
    setError(null);
    getRfqs({
      search: search || undefined,
      orgId,
      boqCategory: boqCategory || undefined,
      page,
      pageSize: PAGE_SIZE,
    })
      .then((res) => {
        setData(res);
        setStatus("ok");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
  }, [search, orgId, boqCategory, page]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total_count / data.page_size)) : 1;

  return (
    <main className="min-h-screen bg-app-gradient">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <header className="mb-6">
          <h1 className="text-xl font-semibold">TAQA Bid Analyzer — Maximo</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Search and filter ADDC procurement tenders from Maximo.
          </p>
        </header>

        <div className="flex flex-wrap gap-3 mb-4 rounded-xl border border-border/60 bg-card p-4">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search RFQ number or description…"
            className="flex-1 min-w-[240px] h-8 rounded-lg border border-border bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <select
            value={orgId}
            onChange={(e) => {
              setOrgId(e.target.value);
              setPage(1);
            }}
            className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
          >
            {ORG_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <select
            value={boqCategory}
            onChange={(e) => {
              setBoqCategory(e.target.value as BoqCategory | "");
              setPage(1);
            }}
            className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
          >
            <option value="">All categories</option>
            {BOQ_CATEGORY_ORDER.map((c) => (
              <option key={c} value={c}>
                {BOQ_CATEGORY_LABELS[c]}
                {data ? ` (${data.category_counts[c].toLocaleString()})` : ""}
              </option>
            ))}
          </select>
        </div>

        {status === "loading" && (
          <p className="text-center py-12 text-muted-foreground animate-pulse">Loading RFQs…</p>
        )}

        {status === "error" && (
          <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-600">
            {error}
          </div>
        )}

        {status === "ok" && data && (
          <>
            <p className="text-sm text-muted-foreground mb-2">
              Showing {data.rfqs.length === 0 ? 0 : (data.page - 1) * data.page_size + 1}–
              {(data.page - 1) * data.page_size + data.rfqs.length} of{" "}
              {data.total_count.toLocaleString()} RFQs
            </p>

            {data.rfqs.length === 0 ? (
              <p className="text-center py-12 text-muted-foreground">No RFQs match your filters.</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-border/60">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-muted/90 backdrop-blur">
                    <tr className="border-b border-border/60 text-left">
                      <th className="px-3 py-2 font-medium">RFQNUM</th>
                      <th className="px-3 py-2 font-medium">Description</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-3 py-2 font-medium">Org</th>
                      <th className="px-3 py-2 font-medium">Entered</th>
                      <th className="px-3 py-2 font-medium text-right">Award Value</th>
                      <th className="px-3 py-2 font-medium">BOQ Category</th>
                      <th className="px-3 py-2 font-medium text-right">Vendors</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rfqs.map((rfq) => (
                      <tr key={rfq.rfqnum} className="odd:bg-muted/[0.15] border-b border-border/40 last:border-0">
                        <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">{rfq.rfqnum}</td>
                        <td className="px-3 py-2 max-w-[360px] truncate" title={rfq.description ?? ""}>
                          {rfq.description ?? "—"}
                        </td>
                        <td className="px-3 py-2">
                          <Badge variant="outline">{rfq.status ?? "—"}</Badge>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {ORG_OPTIONS.find((o) => o.value === rfq.org_id)?.label ?? rfq.org_id ?? "—"}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">{formatDate(rfq.enter_date)}</td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">{formatAED(rfq.total_award_value)}</td>
                        <td className="px-3 py-2">
                          <Badge variant={BOQ_CATEGORY_BADGE_VARIANT[rfq.boq_category]}>
                            {BOQ_CATEGORY_LABELS[rfq.boq_category]}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-right">{rfq.vendor_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex items-center justify-between mt-4">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={data.page <= 1}
                className="h-8 rounded-lg border border-border bg-background px-3 text-sm disabled:opacity-50 disabled:pointer-events-none hover:bg-muted"
              >
                Prev
              </button>
              <span className="text-sm text-muted-foreground">
                Page {data.page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={data.page >= totalPages}
                className="h-8 rounded-lg border border-border bg-background px-3 text-sm disabled:opacity-50 disabled:pointer-events-none hover:bg-muted"
              >
                Next
              </button>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
