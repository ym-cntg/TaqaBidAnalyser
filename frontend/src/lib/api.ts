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
    }
  >;
  match_method: "exact" | "normalized" | "fuzzy" | "llm" | "unmatched";
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
