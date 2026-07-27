const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchAPI<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

async function postAPI<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

async function deleteAPI<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export interface Bidder {
  name: string;
  data_gap: string | null;
}

export interface BOQItem {
  item_no: string;
  description: string;
  unit: string | null;
  qty: number | null;
  cif_unit_rate: number | null;
  cif_total: number | null;
  erection_unit_rate: number | null;
  erection_total: number | null;
  total: number | null;
  is_section_header: boolean;
  raw_cif: string | null;
  raw_erection: string | null;
  is_corrected: boolean;
  is_missing: boolean;
}

export type EditableItemField =
  | "description"
  | "unit"
  | "qty"
  | "cif_unit_rate"
  | "cif_total"
  | "erection_unit_rate"
  | "erection_total"
  | "total";

export interface BOQSheet {
  name: string;
  items: BOQItem[];
  item_count: number;
}

export interface BOQLot {
  lot_name: string;
  lot_number: number;
  sheets: BOQSheet[];
  total_cif: number | null;
  total_erection: number | null;
  total_price: number | null;
  total_items: number;
}

export interface BOQExtraction {
  tender_no: string;
  bidder: string;
  round_name: string;
  lots: BOQLot[];
  total_contract_price: number | null;
  data_gap: string | null;
}

export interface Recommendation {
  lot_number: number;
  item_no: string;
  description: string;
  recommended_cif_total: number;
  recommended_erection_total: number;
  peer_count: number;
}

export interface ComparisonItem {
  item_no: string;
  description: string;
  unit: string | null;
  qty: number | null;
  bidder_prices: Record<
    string,
    {
      cif_total: number | null;
      erection_total: number | null;
      total: number | null;
      is_corrected: boolean;
      is_missing: boolean;
      original_item_no: string | null;
    }
  >;
  match_method: "exact" | "normalized" | "fuzzy" | "llm" | "manual" | "unmatched";
  match_confidence: number;
}

export interface LotComparison {
  lot_name: string;
  lot_number: number;
  items: ComparisonItem[];
  bidder_totals: Record<string, { cif: number | null; erection: number | null; total: number | null }>;
  item_count: number;
}

export interface Flag {
  severity: "critical" | "warning" | "info";
  category: string;
  bidder: string;
  lot: string;
  item_no: string;
  description: string;
  detail: string;
}

export interface ComparisonResult {
  tender_no: string;
  round_name: string;
  lots: LotComparison[];
  flags: Flag[];
  bidder_grand_totals: Record<string, number | null>;
  flag_summary: { critical: number; warning: number; info: number };
}

export async function getBidders(): Promise<Bidder[]> {
  return fetchAPI("/api/sample/bidders");
}

export async function extractBidder(bidder: string): Promise<BOQExtraction> {
  return fetchAPI(`/api/sample/extract/${encodeURIComponent(bidder)}`);
}

export async function getComparison(): Promise<ComparisonResult> {
  return fetchAPI("/api/sample/compare");
}

export interface MatchOverride {
  lot_number: number;
  bidder: string;
  original_item_no: string;
  canonical_item_no: string;
}

export async function getMatchOverrides(): Promise<MatchOverride[]> {
  return fetchAPI("/api/sample/compare/match-overrides");
}

export async function setMatchOverride(
  lotNumber: number,
  bidder: string,
  originalItemNo: string,
  canonicalItemNo: string
): Promise<ComparisonResult> {
  return postAPI("/api/sample/compare/match-override", {
    lot_number: lotNumber,
    bidder,
    original_item_no: originalItemNo,
    canonical_item_no: canonicalItemNo,
  });
}

export async function clearMatchOverride(
  lotNumber: number,
  bidder: string,
  originalItemNo: string
): Promise<ComparisonResult> {
  return postAPI("/api/sample/compare/match-override/clear", {
    lot_number: lotNumber,
    bidder,
    original_item_no: originalItemNo,
  });
}

export async function correctItem(
  bidder: string,
  lotNumber: number,
  sheetName: string,
  itemNo: string,
  fields: Partial<Record<EditableItemField, string | number | null>>
): Promise<BOQExtraction> {
  return postAPI(`/api/sample/extract/${encodeURIComponent(bidder)}/correct`, {
    lot_number: lotNumber,
    sheet_name: sheetName,
    item_no: itemNo,
    fields,
  });
}

export async function revertItem(
  bidder: string,
  lotNumber: number,
  sheetName: string,
  itemNo: string
): Promise<BOQExtraction> {
  return postAPI(`/api/sample/extract/${encodeURIComponent(bidder)}/revert`, {
    lot_number: lotNumber,
    sheet_name: sheetName,
    item_no: itemNo,
  });
}

export async function getRecommendations(bidder: string): Promise<Record<string, Recommendation>> {
  return fetchAPI(`/api/sample/extract/${encodeURIComponent(bidder)}/recommendations`);
}

export interface ReportRecommendation {
  primary_award: string | null;
  shortlist: string[];
  reasoning: string;
}

export interface ReportBidderNote {
  position: "lowest" | "competitive" | "highest" | "excluded_data_gap" | "unknown";
  summary: string;
  negotiation_points: string[];
  flags_highlighted: string[];
}

export interface RecommendationReport {
  executive_summary: string;
  recommendation: ReportRecommendation;
  bidder_notes: Record<string, ReportBidderNote>;
  caveats: string[];
}

export interface ReportStatus {
  cached: boolean;
  generated_at: string | null;
  llm_configured: boolean;
  stale: boolean;
}

export interface ReportGenerateResponse {
  report: RecommendationReport;
  generated_at: string;
  from_cache: boolean;
}

export class ReportUnavailableError extends Error {
  reason: "not_configured" | "api_error" | "parse_error";
  constructor(reason: "not_configured" | "api_error" | "parse_error", message: string) {
    super(message);
    this.reason = reason;
  }
}

export async function getReportStatus(): Promise<ReportStatus> {
  return fetchAPI("/api/sample/report/status");
}

export async function generateReport(force = false): Promise<ReportGenerateResponse> {
  const res = await fetch(`${API_BASE}/api/sample/report/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    if (detail?.reason && detail?.message) {
      throw new ReportUnavailableError(detail.reason, detail.message);
    }
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export function reportExportUrl(kind: "xlsx" | "html"): string {
  return `${API_BASE}/api/sample/report/export.${kind}`;
}

// ---- Projects ----

export interface Project {
  id: string;
  name: string;
  tender_no: string;
  description: string;
  root: string;
  analysis_ready: boolean;
  created_by: string;
  created_at: string;
  bidder_count: number;
  file_count: number;
  selected_count: number;
  exists: boolean;
}

export interface ProjectCreateRequest {
  name: string;
  tender_no: string;
  description: string;
  root: string;
  created_by: string;
}

export async function getProjects(): Promise<Project[]> {
  return fetchAPI("/api/projects");
}

export async function getProjectDetail(projectId: string): Promise<Project> {
  return fetchAPI(`/api/projects/${encodeURIComponent(projectId)}`);
}

export async function createProject(body: ProjectCreateRequest): Promise<Project> {
  return postAPI("/api/projects", body);
}

export async function deleteProject(projectId: string): Promise<{ deleted: string }> {
  return deleteAPI(`/api/projects/${encodeURIComponent(projectId)}`);
}

export async function getDiscoverableRoots(): Promise<string[]> {
  return fetchAPI("/api/projects/discoverable-roots");
}

export interface ProjectFile {
  path: string;
  name: string;
  ext: string;
  size: number;
  selected: boolean;
}

export interface ProjectBidderFiles {
  bidder: string;
  files: ProjectFile[];
  selected_count: number;
}

export interface ProjectFilesResponse {
  id: string;
  tender_no: string;
  label: string;
  bidders: ProjectBidderFiles[];
}

export async function getProjectFiles(projectId: string): Promise<ProjectFilesResponse> {
  return fetchAPI(`/api/projects/${encodeURIComponent(projectId)}/files`);
}

export async function setFileSelection(
  projectId: string,
  bidder: string,
  path: string,
  selected: boolean
): Promise<{ bidder: string; path: string; selected: boolean }> {
  return postAPI(`/api/projects/${encodeURIComponent(projectId)}/selection`, {
    bidder,
    path,
    selected,
  });
}

// ---- Insights dashboard ----

export interface RankedTotal {
  bidder: string;
  grand_total: number | null;
  rank: number | null;
}

export interface Spread {
  min: number;
  max: number;
  median: number;
  spread_pct: number | null;
}

export interface LotSpread {
  lot_name: string;
  lot_number: number;
  spread: Spread | null;
}

export interface InsightsResponse {
  tender_no: string;
  round_name: string;
  ranked_totals: RankedTotal[];
  data_gap_bidders: Record<string, string>;
  flag_counts: Record<string, { by_severity: Record<string, number>; by_category: Record<string, number> }>;
  flag_summary: { critical: number; warning: number; info: number };
  contract_spread: Spread | null;
  lot_spread: LotSpread[];
  flags: Flag[];
}

export async function getInsights(): Promise<InsightsResponse> {
  return fetchAPI("/api/sample/insights");
}

export function comparisonExportUrl(): string {
  return `${API_BASE}/api/sample/comparison/export.xlsx`;
}

// ---- Round-over-round movement ----

export interface RoundPoint {
  round_name: string;
  total_contract_price: number | null;
  lot_totals: Record<string, number | null>;
}

export interface BidderRoundTrend {
  bidder: string;
  points: RoundPoint[];
}

export interface RoundTrendResponse {
  rounds_present: string[];
  bidders: BidderRoundTrend[];
  flags: Flag[];
}

export async function getRoundTrend(): Promise<RoundTrendResponse> {
  return fetchAPI("/api/sample/rounds");
}

// ---- BOQ template workflow (simulated Maximo) ----

export type WorkflowStage =
  | "not_started"
  | "requisition_pulled"
  | "template_built"
  | "template_locked"
  | "issued"
  | "closed";

export interface RequisitionCategory {
  category: string;
  lots: number;
  note: string;
}

export interface Requisition {
  pr_number: string;
  title: string;
  requested_by: string;
  department: string;
  categories: RequisitionCategory[];
}

export interface AwardDecision {
  primary_award: string | null;
  shortlist: string[];
  reasoning: string;
  notes: string;
}

export interface WorkflowStatus {
  project_id: string;
  stage: WorkflowStage;
  requisition: Requisition | null;
  has_template: boolean;
  locked_at: string | null;
  locked_by: string | null;
  issued_at: string | null;
  maximo_reference: string | null;
  closed_at: string | null;
  award_decision: AwardDecision | null;
}

export interface TemplateRow {
  item_no: string;
  description: string;
  unit: string | null;
  qty: number | null;
  is_section_header: boolean;
}

export interface TemplateSheet {
  name: string;
  items: TemplateRow[];
}

export interface TemplateLot {
  lot_name: string;
  lot_number: number;
  sheets: TemplateSheet[];
}

export interface BoqTemplate {
  tender_no: string;
  reference_bidder: string;
  lots: TemplateLot[];
}

export async function getWorkflowStatus(projectId: string): Promise<WorkflowStatus> {
  return fetchAPI(`/api/workflow/${encodeURIComponent(projectId)}/status`);
}

export async function pullRequisition(
  projectId: string
): Promise<{ simulated: boolean; requisition: Requisition; stage: WorkflowStage }> {
  return postAPI(`/api/workflow/${encodeURIComponent(projectId)}/pull-requisition`, {});
}

export async function getTemplate(
  projectId: string
): Promise<{ template: BoqTemplate; stage: WorkflowStage }> {
  return fetchAPI(`/api/workflow/${encodeURIComponent(projectId)}/template`);
}

export async function buildTemplate(
  projectId: string
): Promise<{ template: BoqTemplate; stage: WorkflowStage }> {
  return postAPI(`/api/workflow/${encodeURIComponent(projectId)}/build-template`, {});
}

export async function editTemplateRow(
  projectId: string,
  lotNumber: number,
  sheetName: string,
  itemNo: string,
  fields: Partial<Record<"description" | "unit" | "qty", string | number | null>>
): Promise<{ template: BoqTemplate; stage: WorkflowStage }> {
  return postAPI(`/api/workflow/${encodeURIComponent(projectId)}/template/edit`, {
    lot_number: lotNumber,
    sheet_name: sheetName,
    item_no: itemNo,
    fields,
  });
}

export async function lockTemplate(
  projectId: string,
  lockedBy: string
): Promise<{ stage: WorkflowStage; locked_by: string; locked_at: string }> {
  return postAPI(`/api/workflow/${encodeURIComponent(projectId)}/template/lock`, { locked_by: lockedBy });
}

export async function unlockTemplate(projectId: string): Promise<{ stage: WorkflowStage }> {
  return postAPI(`/api/workflow/${encodeURIComponent(projectId)}/template/unlock`, {});
}

export async function issueTemplate(
  projectId: string
): Promise<{ simulated: boolean; stage: WorkflowStage; issued_at: string; maximo_reference: string }> {
  return postAPI(`/api/workflow/${encodeURIComponent(projectId)}/template/issue`, {});
}

export async function closeProcurement(
  projectId: string,
  body: { primary_award: string | null; shortlist: string[]; reasoning: string; notes: string }
): Promise<{ stage: WorkflowStage; closed_at: string; award_decision: AwardDecision }> {
  return postAPI(`/api/workflow/${encodeURIComponent(projectId)}/close`, body);
}

export async function resetWorkflow(projectId: string): Promise<{ stage: WorkflowStage }> {
  return postAPI(`/api/workflow/${encodeURIComponent(projectId)}/reset`, {});
}
