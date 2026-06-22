from __future__ import annotations

from pathlib import Path

from src.analysis.comparator import compare_lot
from src.analysis.outliers import detect_outliers
from src.analysis.round_tracker import track_rounds
from src.analysis.unbalanced import detect_unbalanced_bidding
from src.analysis.validator import validate_all
from src.config import BOQConfig
from src.extraction.discovery import discover_files
from src.extraction.router import extract_source_file
from src.models import ExtractedBOQ, ExtractedSummary, FileFormat, TenderData
from src.reporting.excel_report import generate_excel_report
from src.reporting.html_report import generate_html_report


def run_analysis(
    tender_id: str,
    tender_name: str,
    data_path: Path,
    config: BOQConfig,
    output_dir: Path,
    target_round: str | None = None,
) -> TenderData:
    """Full pipeline: discover → extract → analyze → report."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Discover files
    print(f"[1/5] Discovering files in {data_path}...")
    source_files = discover_files(data_path)
    print(f"  Found {len(source_files)} files from "
          f"{len({s.bidder for s in source_files})} bidders")

    tender = TenderData(
        tender_id=tender_id,
        name=tender_name,
        source_files=source_files,
    )

    # Step 2: Extract
    print("[2/5] Extracting data from bid documents...")
    excel_count = 0
    pdf_count = 0
    skip_count = 0

    # Process Excel files first, then PDF only when no Excel exists
    # for the same bidder/round/lot
    excel_sources = [s for s in source_files if s.format == FileFormat.EXCEL]
    pdf_sources = [s for s in source_files if s.format == FileFormat.PDF]

    extracted_keys: set[tuple[str, str, str | None]] = set()  # (bidder, round, lot)

    for source in excel_sources:
        try:
            result = extract_source_file(source, config)
            if result is None:
                skip_count += 1
                continue

            if isinstance(result, ExtractedBOQ):
                tender.extractions.append(result)
                excel_count += 1
                extracted_keys.add((source.bidder, source.round, source.lot))
            elif isinstance(result, ExtractedSummary):
                tender.summaries.append(result)
                extracted_keys.add((source.bidder, source.round, source.lot))

        except Exception as e:
            print(f"  [ERROR] {source.path.name}: {e}")
            skip_count += 1

    for source in pdf_sources:
        key = (source.bidder, source.round, source.lot)
        if key in extracted_keys:
            skip_count += 1
            continue

        try:
            result = extract_source_file(source, config)
            if result is None:
                skip_count += 1
                continue

            if isinstance(result, ExtractedBOQ):
                tender.extractions.append(result)
                pdf_count += 1
                extracted_keys.add(key)
            elif isinstance(result, ExtractedSummary):
                tender.summaries.append(result)

        except Exception as e:
            print(f"  [ERROR] {source.path.name}: {e}")
            skip_count += 1

    print(f"  Extracted: {excel_count} Excel, {pdf_count} PDF, "
          f"{len(tender.summaries)} summaries, {skip_count} skipped")

    # Determine which round to analyze
    if target_round is None:
        # Use the latest round that has the most bidder coverage
        target_round = _best_round(tender)
    print(f"  Primary analysis round: {target_round}")

    # Step 3: Validate
    print("[3/5] Running validation checks...")
    tender.findings.extend(validate_all(tender))
    print(f"  Validation findings: {len(tender.findings)}")

    # Step 4: Analyze
    print("[4/5] Running analysis (outliers, unbalanced bidding)...")
    tender.findings.extend(detect_outliers(tender, target_round))
    tender.findings.extend(detect_unbalanced_bidding(tender, target_round))

    high = sum(1 for f in tender.findings if f.severity.value == "high")
    med = sum(1 for f in tender.findings if f.severity.value == "medium")
    print(f"  Total findings: {len(tender.findings)} ({high} high, {med} medium)")

    # Round tracking
    round_summary = track_rounds(tender)

    # Step 5: Report
    print("[5/5] Generating reports...")

    excel_path = output_dir / f"{tender_id}_comparison_{target_round}.xlsx"
    generate_excel_report(tender, target_round, round_summary, excel_path)
    print(f"  Excel: {excel_path}")

    html_path = output_dir / f"{tender_id}_report_{target_round}.html"
    generate_html_report(tender, target_round, round_summary, html_path)
    print(f"  HTML:  {html_path}")

    # Print summary
    _print_summary(tender, target_round)

    return tender


def _best_round(tender: TenderData) -> str:
    """Find the round with the most bidder coverage."""
    round_bidder_count: dict[str, int] = {}
    for ext in tender.extractions:
        key = ext.round
        if key not in round_bidder_count:
            round_bidder_count[key] = 0
        round_bidder_count[key] += 1

    if not round_bidder_count:
        return "original"

    return max(round_bidder_count, key=lambda r: round_bidder_count[r])


def _print_summary(tender: TenderData, round_name: str) -> None:
    print("\n" + "=" * 70)
    print(f"  TENDER: {tender.tender_id} — {tender.name}")
    print(f"  ROUND:  {round_name}")
    print("=" * 70)

    print(f"\n  Bidders ({len(tender.bidders)}):")
    for bidder in tender.bidders:
        lots_data = []
        grand_total = 0.0
        for lot in tender.lots:
            ext = tender.get_extraction(bidder, round_name, lot)
            if ext and ext.total_price:
                lots_data.append(f"{lot}: {ext.total_price:,.0f}")
                grand_total += ext.total_price
            else:
                lots_data.append(f"{lot}: —")

        bidder_findings = [f for f in tender.findings if f.bidder == bidder]
        flag_str = ""
        if bidder_findings:
            flag_str = f" [{len(bidder_findings)} findings]"

        print(f"    {bidder}: {grand_total:>15,.0f} AED  ({', '.join(lots_data)}){flag_str}")

    finding_cats: dict[str, int] = {}
    for f in tender.findings:
        cat = f.category.value
        finding_cats[cat] = finding_cats.get(cat, 0) + 1

    if finding_cats:
        print(f"\n  Findings Summary:")
        for cat, count in sorted(finding_cats.items()):
            print(f"    {cat}: {count}")

    print()
