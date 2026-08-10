"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getComparison, type ComparisonResponse } from "@/lib/api";
import { formatAED, formatNumber } from "@/lib/format";

function vendorLabel(vendor: string, name: string | null): string {
  return name ?? vendor;
}

export function RfqComparison({ rfqnum }: { rfqnum: string }) {
  const [data, setData] = useState<ComparisonResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setStatus("loading");
    setError(null);
    getComparison(rfqnum)
      .then((res) => {
        setData(res);
        setStatus("ok");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
  }, [rfqnum]);

  if (status === "loading") {
    return (
      <Card>
        <CardContent className="py-6 text-center text-sm text-muted-foreground animate-pulse">
          Loading comparison…
        </CardContent>
      </Card>
    );
  }

  if (status === "error") {
    return (
      <Card>
        <CardContent className="py-6">
          <div className="rounded-lg border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-600">
            {error}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  if (data.vendors.length === 0) {
    return (
      <Card>
        <CardContent className="py-6 text-center text-sm text-muted-foreground">
          No vendor pricing found for this RFQ yet.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Bidder summary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-xl border border-border/60">
            <table className="w-full text-sm">
              <thead className="bg-muted/90">
                <tr className="border-b border-border/60 text-left">
                  <th className="px-3 py-2 font-medium">Vendor</th>
                  <th className="px-3 py-2 font-medium text-right">Contract total</th>
                  <th className="px-3 py-2 font-medium">Flags</th>
                </tr>
              </thead>
              <tbody>
                {data.vendors.map((v) => (
                  <tr key={v.vendor} className="odd:bg-muted/[0.15] border-b border-border/40 last:border-0">
                    <td className="px-3 py-2">
                      <div>{vendorLabel(v.vendor, v.name)}</div>
                      <div className="font-mono text-xs text-muted-foreground">{v.vendor}</div>
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">{formatAED(v.contract_total)}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {v.unquoted_count > 0 && <Badge variant="outline">{v.unquoted_count} unquoted</Badge>}
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
                ))}
              </tbody>
            </table>
          </div>

          {data.not_submitted.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              Invited but did not submit any pricing:{" "}
              {data.not_submitted.map((v) => vendorLabel(v.vendor, v.name)).join(", ")}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Line-item comparison</CardTitle>
        </CardHeader>
        <CardContent>
          {data.truncated && (
            <p className="mb-3 text-xs text-muted-foreground">
              Showing first {data.lines.length.toLocaleString()} of {data.total_line_count.toLocaleString()}{" "}
              lines.
            </p>
          )}
          <div className="max-h-[600px] overflow-auto rounded-xl border border-border/60">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted/90 backdrop-blur">
                <tr className="border-b border-border/60 text-left">
                  <th className="px-3 py-2 font-medium">Line</th>
                  <th className="px-3 py-2 font-medium">Description</th>
                  <th className="px-3 py-2 font-medium text-right">Qty</th>
                  {data.vendors.map((v) => (
                    <th key={v.vendor} className="px-3 py-2 font-medium text-right whitespace-nowrap">
                      {vendorLabel(v.vendor, v.name)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.lines.map((line) => (
                  <tr
                    key={line.rfqlinenum}
                    className="odd:bg-muted/[0.15] border-b border-border/40 last:border-0"
                  >
                    <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">{line.rfqlinenum}</td>
                    <td className="px-3 py-2 max-w-[280px] truncate" title={line.description ?? ""}>
                      {line.description ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap text-xs text-muted-foreground">
                      {line.qty != null ? formatNumber(line.qty) : "—"} {line.unit ?? ""}
                    </td>
                    {data.vendors.map((v) => {
                      const p = line.prices[v.vendor];
                      if (!p || p.unquoted) {
                        return (
                          <td key={v.vendor} className="px-3 py-2 text-right text-muted-foreground">
                            —
                          </td>
                        );
                      }
                      return (
                        <td
                          key={v.vendor}
                          className={`px-3 py-2 text-right whitespace-nowrap ${
                            p.is_lowest ? "bg-green-500/10 font-medium" : ""
                          }`}
                        >
                          <span className="inline-flex items-center gap-1">
                            {p.arithmetic_error && (
                              <span
                                className="inline-block size-1.5 rounded-full bg-red-500"
                                title="Line total doesn't match qty × unit rate"
                              />
                            )}
                            {p.outlier && (
                              <span
                                className="inline-block size-1.5 rounded-full bg-amber-500"
                                title="Unusually far from other bidders' price on this line"
                              />
                            )}
                            {formatAED(p.line_cost)}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
