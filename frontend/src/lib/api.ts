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
  zero_price: boolean;
  corrected: boolean;
  corrected_by_label: string | null;
  corrected_note: string | null;
  corrected_at: string | null;
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
  zero_price_count: number;
}

export interface NotSubmittedVendor {
  vendor: string;
  name: string | null;
}

export interface ComparisonResponse {
  rfqnum: string;
  round: string;
  rounds_present: string[];
  total_line_count: number;
  truncated: boolean;
  vendors: ComparisonVendor[];
  not_submitted: NotSubmittedVendor[];
  lines: ComparisonLine[];
}

export async function getComparison(rfqnum: string, round?: string): Promise<ComparisonResponse> {
  const qs = round ? `?round=${encodeURIComponent(round)}` : "";
  const res = await fetch(`/api/rfqs/${encodeURIComponent(rfqnum)}/comparison${qs}`);
  return handleJson<ComparisonResponse>(res);
}

export interface CreateCorrectionParams {
  rfqnum: string;
  rfqlinenum: number;
  vendor: string;
  unitCost: number;
  userId: string;
  note?: string;
}

export interface CorrectionSummary {
  rfqlinenum: number;
  vendor: string;
  unit_cost: number;
  line_cost: number | null;
  note: string | null;
  corrected_by_label: string | null;
  corrected_at: string;
}

export async function createCorrection(params: CreateCorrectionParams): Promise<CorrectionSummary> {
  const res = await fetch(`/api/rfqs/${encodeURIComponent(params.rfqnum)}/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rfqlinenum: params.rfqlinenum,
      vendor: params.vendor,
      unit_cost: params.unitCost,
      user_id: params.userId,
      note: params.note ?? null,
    }),
  });
  return handleJson<CorrectionSummary>(res);
}

export interface RoundPoint {
  round: string;
  contract_total: number | null;
  date: string | null;
}

export interface VendorRoundTrend {
  vendor: string;
  name: string | null;
  points: RoundPoint[];
}

export interface RoundFlag {
  severity: "critical" | "warning";
  vendor: string;
  name: string | null;
  rfqlinenum: number;
  description: string | null;
  detail: string;
}

export interface RoundTrendResponse {
  rfqnum: string;
  rounds_present: string[];
  vendors: VendorRoundTrend[];
  flags: RoundFlag[];
}

export async function getRoundTrend(rfqnum: string): Promise<RoundTrendResponse> {
  const res = await fetch(`/api/rfqs/${encodeURIComponent(rfqnum)}/rounds`);
  return handleJson<RoundTrendResponse>(res);
}

export interface TopIssue {
  source: "boq" | "round";
  severity: "critical" | "warning";
  rfqlinenum: number;
  description: string | null;
  detail: string;
}

export interface NegotiationVendorSummary {
  vendor: string;
  name: string | null;
  rank: number;
  contract_total: number;
  pct_above_lowest: number;
  unquoted_count: number;
  arithmetic_error_count: number;
  outlier_count: number;
  zero_price_count: number;
  round_critical_count: number;
  round_warning_count: number;
  top_issues: TopIssue[];
}

export interface NegotiationReportResponse {
  rfqnum: string;
  generated_at: string;
  has_round_data: boolean;
  vendors: NegotiationVendorSummary[];
  not_submitted: NotSubmittedVendor[];
}

export async function getNegotiationReport(rfqnum: string): Promise<NegotiationReportResponse> {
  const res = await fetch(`/api/rfqs/${encodeURIComponent(rfqnum)}/negotiation-report`);
  return handleJson<NegotiationReportResponse>(res);
}

export function negotiationReportExportUrl(rfqnum: string): string {
  return `/api/rfqs/${encodeURIComponent(rfqnum)}/negotiation-report.xlsx`;
}

export interface NarrativeObservation {
  vendor: string;
  note: string;
  talking_points: string[];
}

export interface NarrativeReport {
  rfqnum: string;
  generated_at: string;
  executive_summary: string;
  observations: NarrativeObservation[];
  caveats: string[];
}

// Distinguishes "the feature isn't set up" (503) from everything else
// (502 -- the model call failed, or came back in an unusable shape) so
// the UI can show setup instructions instead of a raw error only in the
// one case that's actually about configuration, not a real failure.
// Shared by every AI feature (negotiation narrative, Beta pricing) --
// the distinction isn't narrative-specific.
export class AiUnavailableError extends Error {
  status: number;
  notConfigured: boolean;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.notConfigured = status === 503;
  }
}

export async function generateNegotiationNarrative(rfqnum: string): Promise<NarrativeReport> {
  const res = await fetch(`/api/rfqs/${encodeURIComponent(rfqnum)}/negotiation-report/narrative`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new AiUnavailableError(res.status, body?.detail ?? `Request failed with status ${res.status}`);
  }
  return res.json();
}

export interface BetaLineEstimate {
  rfqlinenum: number;
  beta_unit_cost: number;
  beta_line_cost: number;
  confidence: "low" | "medium" | "high";
  rationale: string;
}

export interface BetaPricingResponse {
  rfqnum: string;
  round: string;
  generated_at: string;
  truncated: boolean;
  total_line_count: number;
  estimated_line_count: number;
  lines: BetaLineEstimate[];
}

export async function generateBetaPricing(rfqnum: string, round?: string): Promise<BetaPricingResponse> {
  const qs = round ? `?round=${encodeURIComponent(round)}` : "";
  const res = await fetch(`/api/rfqs/${encodeURIComponent(rfqnum)}/comparison/beta${qs}`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new AiUnavailableError(res.status, body?.detail ?? `Request failed with status ${res.status}`);
  }
  return res.json();
}
