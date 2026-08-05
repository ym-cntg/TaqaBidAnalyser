import type { BoqCategory } from "@/lib/api";

// DETAILBOQAVAILABLE (the flag on rfq) is confirmed unreliable -- these
// categories are computed server-side from real quotationline row counts.
// See databricks/FINDINGS.md.

export const BOQ_CATEGORY_ORDER: BoqCategory[] = [
  "detailed_boq",
  "shallow",
  "lump_sum",
  "no_pricing_data",
];

export const BOQ_CATEGORY_LABELS: Record<BoqCategory, string> = {
  detailed_boq: "Detailed BOQ",
  shallow: "Shallow",
  lump_sum: "Lump-sum",
  no_pricing_data: "No pricing data",
};

// shadcn Badge variants: default | secondary | destructive | outline | ghost | link
export const BOQ_CATEGORY_BADGE_VARIANT: Record<BoqCategory, "default" | "secondary" | "outline" | "ghost"> = {
  detailed_boq: "default",
  shallow: "secondary",
  lump_sum: "outline",
  no_pricing_data: "ghost",
};
