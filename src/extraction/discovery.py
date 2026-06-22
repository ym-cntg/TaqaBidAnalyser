from __future__ import annotations

from pathlib import Path

from src.config import LOT_PATTERNS, ROUND_ALIASES, SUMMARY_PATTERNS
from src.models import FileFormat, SourceFile


def _identify_lot(filename: str) -> str | None:
    name_lower = filename.lower()
    for lot_id, patterns in LOT_PATTERNS.items():
        if any(p in name_lower for p in patterns):
            return lot_id
    return None


def _is_summary_file(filename: str) -> bool:
    name_lower = filename.lower().replace(" ", "").replace("_", "")
    return any(p in name_lower for p in SUMMARY_PATTERNS)


def _normalize_round(round_dir: str) -> str:
    return ROUND_ALIASES.get(round_dir.lower(), round_dir.lower())


def discover_files(tender_path: Path) -> list[SourceFile]:
    """Walk a tender directory and identify all bid documents.

    Expected structure:
        tender_path/
            {BidderName}/
                {round}/       # original, round1, round2, ...
                    excel/     # .xlsx files
                    pdf/       # .pdf files
    """
    source_files: list[SourceFile] = []

    if not tender_path.is_dir():
        raise FileNotFoundError(f"Tender path not found: {tender_path}")

    for bidder_dir in sorted(tender_path.iterdir()):
        if not bidder_dir.is_dir():
            continue

        bidder_name = bidder_dir.name

        for round_dir in sorted(bidder_dir.iterdir()):
            if not round_dir.is_dir():
                continue

            round_name = _normalize_round(round_dir.name)

            # Handle nested option folders (e.g., POWER LINES/round3/Option1/)
            format_dirs = _find_format_dirs(round_dir)

            for format_dir, prefix in format_dirs:
                file_format = (
                    FileFormat.EXCEL if format_dir.name == "excel"
                    else FileFormat.PDF
                )

                for file_path in sorted(format_dir.iterdir()):
                    if not file_path.is_file():
                        continue
                    if file_path.name.startswith("~"):
                        continue

                    ext = file_path.suffix.lower()
                    if file_format == FileFormat.EXCEL and ext != ".xlsx":
                        continue
                    if file_format == FileFormat.PDF and ext != ".pdf":
                        continue

                    lot = None
                    if _is_summary_file(file_path.name):
                        lot = "summary"
                    else:
                        lot = _identify_lot(file_path.name)

                    # Prefix lot with option if in a sub-option folder
                    effective_lot = lot
                    if prefix and lot and lot != "summary":
                        effective_lot = f"{lot} ({prefix})"
                    elif prefix and lot == "summary":
                        effective_lot = f"summary ({prefix})"

                    source_files.append(SourceFile(
                        path=file_path,
                        format=file_format,
                        bidder=bidder_name,
                        round=round_name,
                        lot=effective_lot,
                    ))

    return source_files


def _find_format_dirs(round_dir: Path) -> list[tuple[Path, str]]:
    """Find excel/ and pdf/ directories, handling optional sub-folders like Option1/."""
    results: list[tuple[Path, str]] = []

    excel_dir = round_dir / "excel"
    pdf_dir = round_dir / "pdf"

    if excel_dir.is_dir():
        results.append((excel_dir, ""))
    if pdf_dir.is_dir():
        results.append((pdf_dir, ""))

    # Check for option sub-folders (e.g., Option1/excel/, Option2/pdf/)
    for sub_dir in sorted(round_dir.iterdir()):
        if not sub_dir.is_dir():
            continue
        if sub_dir.name in ("excel", "pdf"):
            continue

        sub_excel = sub_dir / "excel"
        sub_pdf = sub_dir / "pdf"
        if sub_excel.is_dir():
            results.append((sub_excel, sub_dir.name))
        if sub_pdf.is_dir():
            results.append((sub_pdf, sub_dir.name))

    return results
