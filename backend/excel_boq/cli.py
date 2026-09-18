"""Command-line entry point: python -m backend.excel_boq.cli <files...>

Exists so the extraction can be exercised against a folder of real
vendor files without starting the app or touching Databricks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.excel_boq.generator import to_dict, to_workbook
from backend.excel_boq.parser import parse_workbook


def _report(document) -> None:
    print(f"\n{document.source_file}")
    print(f"  tender:      {document.tender_ref or 'not found'}")
    print(f"  line items:  {document.item_count}")
    print(f"  total:       {document.grand_total:,.2f}")

    reconciliation = document.reconciliation
    if reconciliation:
        verdict = "OK" if reconciliation.agrees else "MISMATCH"
        print(
            f"  vendor says: {reconciliation.stated_total:,.2f}  "
            f"[{verdict} {reconciliation.percent:.2f}%]"
        )

    for sheet in document.sheets:
        print(
            f"    [{sheet.role:7}] {sheet.sheet_name[:34]:34} "
            f"{sheet.item_count:>4} items  {sheet.total:>16,.2f}"
        )
    for skipped in document.skipped:
        print(f"    [skipped] {skipped.sheet_name[:34]:34} {skipped.reason}")

    errors = document.arithmetic_errors
    if errors:
        print(f"  arithmetic errors: {len(errors)}")
        for sheet_name, line in errors[:5]:
            print(f"    {sheet_name} row {line.row_number} ({line.item_no}): {line.arithmetic_error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract a BOQ from vendor Excel files.")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--xlsx", type=Path, help="write the normalized BOQ workbook here")
    parser.add_argument("--json", type=Path, help="write the parsed BOQ as JSON here")
    parser.add_argument("--quiet", action="store_true", help="suppress the per-file report")
    args = parser.parse_args(argv)

    documents = []
    failures = 0
    for path in args.files:
        if not path.exists():
            print(f"  not found: {path}", file=sys.stderr)
            failures += 1
            continue
        try:
            document = parse_workbook(path, path.name)
        except Exception as exc:
            print(f"  failed: {path.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            failures += 1
            continue
        documents.append(document)
        if not args.quiet:
            _report(document)

    if args.json and documents:
        payload = [to_dict(document) for document in documents]
        args.json.write_text(json.dumps(payload, indent=2, default=str))
        print(f"\nwrote {args.json}")

    if args.xlsx and documents:
        if len(documents) > 1:
            print("  --xlsx takes a single input file", file=sys.stderr)
            return 1
        args.xlsx.write_bytes(to_workbook(documents[0]).getvalue())
        print(f"wrote {args.xlsx}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
