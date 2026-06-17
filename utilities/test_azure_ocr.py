"""Test Azure Document Intelligence on a PDF file.

Usage:
    python utilities/test_azure_ocr.py <input_pdf> [output_path]

Examples:
    python utilities/test_azure_ocr.py "data/power/AL Geemi/original/pdf/CommercialSubmission(D-111808).pdf"
    python utilities/test_azure_ocr.py input.pdf output/result.txt
    python utilities/test_azure_ocr.py input.pdf output/result.json --format json

If output_path is omitted, writes to utilities/output/<input_filename>.txt
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential


def get_client() -> DocumentIntelligenceClient:
    endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    if not endpoint or not key:
        print("Error: Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
              "AZURE_DOCUMENT_INTELLIGENCE_KEY in .env")
        sys.exit(1)
    return DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )


def analyze_pdf(filepath: Path, pages: str | None = None) -> dict:
    """Send PDF to Azure and return the analysis result."""
    client = get_client()

    with open(filepath, "rb") as f:
        pdf_bytes = f.read()

    print(f"Sending {filepath.name} ({len(pdf_bytes) / 1024:.0f} KB) to Azure...")
    start = time.time()

    kwargs = {}
    if pages:
        kwargs["pages"] = pages

    poller = client.begin_analyze_document(
        "prebuilt-layout",
        AnalyzeDocumentRequest(bytes_source=pdf_bytes),
        **kwargs,
    )
    result = poller.result()
    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s")

    return result


def format_as_text(result) -> str:
    """Format Azure result as readable text."""
    lines = []
    lines.append("=" * 80)
    lines.append("AZURE DOCUMENT INTELLIGENCE — EXTRACTION RESULT")
    lines.append("=" * 80)
    lines.append("")

    # Content summary
    content = result.content or ""
    lines.append(f"Total characters extracted: {len(content)}")
    lines.append(f"Pages: {len(result.pages or [])}")
    lines.append(f"Tables: {len(result.tables or [])}")
    lines.append("")

    # Full extracted text
    lines.append("-" * 80)
    lines.append("EXTRACTED TEXT")
    lines.append("-" * 80)
    lines.append(content)
    lines.append("")

    # Tables
    for t_idx, table in enumerate(result.tables or []):
        lines.append("-" * 80)
        lines.append(f"TABLE {t_idx + 1} ({table.row_count} rows x {table.column_count} cols)")
        lines.append("-" * 80)

        grid = [[""] * table.column_count for _ in range(table.row_count)]
        for cell in table.cells:
            grid[cell.row_index][cell.column_index] = cell.content or ""

        # Calculate column widths
        col_widths = []
        for col in range(table.column_count):
            max_w = max((len(grid[row][col]) for row in range(table.row_count)), default=5)
            col_widths.append(min(max_w, 40))

        for row_idx, row in enumerate(grid):
            cells = [cell[:40].ljust(col_widths[i]) for i, cell in enumerate(row)]
            lines.append(" | ".join(cells))
            if row_idx == 0:
                lines.append("-+-".join("-" * w for w in col_widths))

        lines.append("")

    return "\n".join(lines)


def format_as_json(result) -> str:
    """Format Azure result as JSON with tables and text."""
    tables = []
    for table in (result.tables or []):
        grid = [[""] * table.column_count for _ in range(table.row_count)]
        for cell in table.cells:
            grid[cell.row_index][cell.column_index] = cell.content or ""
        tables.append({
            "row_count": table.row_count,
            "column_count": table.column_count,
            "rows": grid,
        })

    output = {
        "content": result.content or "",
        "page_count": len(result.pages or []),
        "table_count": len(result.tables or []),
        "tables": tables,
    }
    return json.dumps(output, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Test Azure Document Intelligence on a PDF")
    parser.add_argument("input_pdf", help="Path to input PDF file")
    parser.add_argument("output_path", nargs="?", help="Output file path (default: utilities/output/<name>.txt)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument("--pages", help="Page range to analyze (e.g. '1-5', '3,5,7')")
    args = parser.parse_args()

    input_path = Path(args.input_pdf)
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    # Determine output path
    if args.output_path:
        output_path = Path(args.output_path)
    else:
        ext = ".json" if args.format == "json" else ".txt"
        output_dir = Path(__file__).parent / "output"
        output_path = output_dir / (input_path.stem + ext)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Run analysis
    result = analyze_pdf(input_path, pages=args.pages)

    # Format and write output
    if args.format == "json":
        output = format_as_json(result)
    else:
        output = format_as_text(result)

    output_path.write_text(output, encoding="utf-8")
    print(f"Output written to: {output_path}")

    # Print quick summary
    print(f"\nSummary:")
    print(f"  Pages analyzed: {len(result.pages or [])}")
    print(f"  Tables found: {len(result.tables or [])}")
    print(f"  Text length: {len(result.content or '')} chars")


if __name__ == "__main__":
    main()
