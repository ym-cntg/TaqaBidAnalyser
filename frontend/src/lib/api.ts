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

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? `Request failed with status ${res.status}`);
  }
  return res.json();
}

export interface UserSummary {
  user_id: string;
  display_name: string;
  source: "forwarded_header" | "self_reported";
}

export async function identifyUser(displayName?: string): Promise<UserSummary> {
  const res = await fetch("/api/users/identify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName ?? null }),
  });
  return handleJson<UserSummary>(res);
}

export interface ProjectSummary {
  project_id: string;
  user_id: string;
  user_display_name: string | null;
  name: string;
  rfqnum: string;
  created_at: string;
  rfq_description: string | null;
  rfq_status: string | null;
  org_id: string | null;
  boq_category: BoqCategory | null;
  vendor_count: number | null;
}

export interface ProjectListResponse {
  projects: ProjectSummary[];
}

export interface CreateProjectParams {
  name: string;
  rfqnum: string;
  userId: string;
}

export async function getProjects(userId?: string): Promise<ProjectListResponse> {
  const qs = new URLSearchParams();
  if (userId) qs.set("user_id", userId);
  const res = await fetch(`/api/projects?${qs.toString()}`);
  return handleJson<ProjectListResponse>(res);
}

export async function getProject(projectId: string): Promise<ProjectSummary> {
  const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}`);
  return handleJson<ProjectSummary>(res);
}

export async function createProject(params: CreateProjectParams): Promise<ProjectSummary> {
  const res = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: params.name, rfqnum: params.rfqnum, user_id: params.userId }),
  });
  return handleJson<ProjectSummary>(res);
}

export interface ComparisonLinePrice {
  unit_cost: number | null;
  line_cost: number | null;
  unquoted: boolean;
  is_lowest: boolean;
  arithmetic_error: boolean;
  outlier: boolean;
}

export interface ComparisonLine {
  rfqlinenum: number;
  description: string | null;
  qty: number | null;
  unit: string | null;
  prices: Record<string, ComparisonLinePrice>;
}

export interface ComparisonVendor {
  vendor: string;
  name: string | null;
  contract_total: number;
  unquoted_count: number;
  arithmetic_error_count: number;
  outlier_count: number;
}

export interface NotSubmittedVendor {
  vendor: string;
  name: string | null;
}

export interface ComparisonResponse {
  rfqnum: string;
  total_line_count: number;
  truncated: boolean;
  vendors: ComparisonVendor[];
  not_submitted: NotSubmittedVendor[];
  lines: ComparisonLine[];
}

export async function getComparison(rfqnum: string): Promise<ComparisonResponse> {
  const res = await fetch(`/api/rfqs/${encodeURIComponent(rfqnum)}/comparison`);
  return handleJson<ComparisonResponse>(res);
}
