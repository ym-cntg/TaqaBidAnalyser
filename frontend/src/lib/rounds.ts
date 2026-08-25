// Shared round-label formatting, used by both the Round Tracking chart and
// the BOQ Comparison round selector so a revision reads the same way in
// both places.
export function formatRoundLabel(round: string): string {
  if (round === "original") return "Original";
  const n = parseFloat(round);
  return `Revision ${Number.isFinite(n) ? n : round}`;
}
