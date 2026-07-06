const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchAPI<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export interface Bidder {
  name: string;
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
}

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
}

export interface ComparisonItem {
  item_no: string;
  description: string;
  unit: string | null;
  qty: number | null;
  bidder_prices: Record<string, { cif_total: number | null; erection_total: number | null; total: number | null }>;
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
