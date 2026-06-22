from __future__ import annotations

from pathlib import Path

from src.config import BOQConfig
from src.models import ExtractedBOQ, ExtractedSummary, FileFormat, SourceFile

from .excel_parser import extract_boq, extract_summary
from .pdf_parser import estimate_confidence, extract_boq_from_pdf

CONFIDENCE_THRESHOLD = 0.6


def extract_source_file(
    source: SourceFile,
    config: BOQConfig,
) -> ExtractedBOQ | ExtractedSummary | None:
    """Route extraction based on file format with confidence-based fallback."""
    if source.lot and source.lot.startswith("summary"):
        return _extract_summary_file(source, config)

    if source.lot is None:
        # Can't determine lot — skip for now
        return None

    if source.format == FileFormat.EXCEL:
        return extract_boq(
            file_path=source.path,
            config=config,
            bidder=source.bidder,
            round_name=source.round,
            lot=source.lot,
        )

    if source.format == FileFormat.PDF:
        return _extract_pdf_with_fallback(source, config)

    return None


def _extract_pdf_with_fallback(
    source: SourceFile,
    config: BOQConfig,
) -> ExtractedBOQ | None:
    """Try PyMuPDF first, fall back to Azure if confidence is low."""
    result = extract_boq_from_pdf(
        file_path=source.path,
        config=config,
        bidder=source.bidder,
        round_name=source.round,
        lot=source.lot or "unknown",
    )

    confidence = estimate_confidence(result, config)

    if confidence >= CONFIDENCE_THRESHOLD:
        return result

    # Try Azure Document Intelligence if available
    try:
        from .azure_parser import extract_boq_from_azure

        return extract_boq_from_azure(
            file_path=source.path,
            config=config,
            bidder=source.bidder,
            round_name=source.round,
            lot=source.lot or "unknown",
        )
    except ImportError:
        # Azure parser not available — return PyMuPDF result with warning
        print(
            f"  [WARN] Low confidence ({confidence:.0%}) for {source.path.name}, "
            f"Azure parser not available"
        )
        return result


def _extract_summary_file(
    source: SourceFile,
    config: BOQConfig,
) -> ExtractedSummary | None:
    if source.format == FileFormat.EXCEL:
        return extract_summary(
            file_path=source.path,
            config=config,
            bidder=source.bidder,
            round_name=source.round,
        )
    # PDF summaries are harder — skip for now
    return None
