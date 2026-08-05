// Centralized number/date formatting -- the old app (full-feature-buildout)
// duplicated a version of formatNum in every page file; keep it here once.

export function formatNumber(val: number | null | undefined): string {
  if (val == null) return "—";
  return new Intl.NumberFormat("en-AE", { maximumFractionDigits: 0 }).format(val);
}

export function formatAED(val: number | null | undefined): string {
  if (val == null) return "—";
  return `AED ${formatNumber(val)}`;
}

export function formatDate(val: string | null | undefined): string {
  if (!val) return "—";
  const d = new Date(val);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-AE", { day: "numeric", month: "short", year: "numeric" }).format(d);
}
