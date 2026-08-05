export type BoqCategory = "detailed_boq" | "shallow" | "lump_sum" | "no_pricing_data";

export interface RfqSummary {
  rfqnum: string;
  description: string | null;
  status: string | null;
  org_id: string | null;
  enter_date: string | null;
  total_award_value: number | null;
  boq_category: BoqCategory;
  vendor_count: number;
}

export interface RfqListResponse {
  rfqs: RfqSummary[];
  total_count: number;
  page: number;
  page_size: number;
  category_counts: Record<BoqCategory, number>;
  boq_stats_updated_at: string | null;
}

export interface RfqListParams {
  search?: string;
  orgId?: string;
  boqCategory?: BoqCategory;
  page?: number;
  pageSize?: number;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function getRfqs(params: RfqListParams = {}): Promise<RfqListResponse> {
  const qs = new URLSearchParams();
  if (params.search) qs.set("search", params.search);
  if (params.orgId) qs.set("org_id", params.orgId);
  if (params.boqCategory) qs.set("boq_category", params.boqCategory);
  if (params.page) qs.set("page", String(params.page));
  if (params.pageSize) qs.set("page_size", String(params.pageSize));

  const res = await fetch(`/api/rfqs?${qs.toString()}`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? `Request failed with status ${res.status}`);
  }
  return res.json();
}
