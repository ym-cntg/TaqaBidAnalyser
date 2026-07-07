"""User corrections layered on top of extracted BOQ data.

OCR/PDF extraction isn't 100% reliable (see BUG_TRACKER.md's DATA-001: a
digit misread that inflated one item 100x). Rather than trust every
extracted value silently, a reviewer can override any field on any item;
that correction then feeds every downstream calculation (lot/contract
totals, the Compare table, flag detection) instead of the original value.

Corrections are stored in-memory only, keyed by bidder name — same
lifetime as the extraction cache in `api/routes.py`. This is a known
scope limit for the POC (lost on server restart), consistent with the
rest of the app's in-memory-only sample-data model.
"""

import dataclasses

from ..extraction.excel_parser import BOQExtraction, BOQItem

EDITABLE_FIELDS = {
    "description",
    "unit",
    "qty",
    "cif_unit_rate",
    "cif_total",
    "erection_unit_rate",
    "erection_total",
    "total",
}

# bidder_name -> (lot_number, sheet_name, item_no) -> {"fields": {...}, "original": {...}}
_corrections: dict[str, dict[tuple[int, str, str], dict]] = {}


def record_correction(
    bidder: str,
    lot_number: int,
    sheet_name: str,
    item_no: str,
    fields: dict,
    raw_item: BOQItem,
) -> dict:
    """Store (or update) a correction. Keeps the *original* OCR/extracted
    values from the first edit, even across repeated edits, so a revert
    or an audit trail always shows the true pristine value."""
    bucket = _corrections.setdefault(bidder, {})
    key = (lot_number, sheet_name, item_no)
    existing = bucket.get(key)
    original = existing["original"] if existing else {
        f: getattr(raw_item, f) for f in EDITABLE_FIELDS
    }
    record = {
        "lot_number": lot_number,
        "sheet_name": sheet_name,
        "item_no": item_no,
        "fields": fields,
        "original": original,
    }
    bucket[key] = record
    return record


def clear_correction(bidder: str, lot_number: int, sheet_name: str, item_no: str) -> None:
    bucket = _corrections.get(bidder)
    if not bucket:
        return
    bucket.pop((lot_number, sheet_name, item_no), None)


def list_corrections(bidder: str) -> list[dict]:
    bucket = _corrections.get(bidder, {})
    return [
        {
            "lot_number": r["lot_number"],
            "sheet_name": r["sheet_name"],
            "item_no": r["item_no"],
            "fields": r["fields"],
            "original": r["original"],
        }
        for r in bucket.values()
    ]


def apply_corrections(ext: BOQExtraction, bidder: str) -> BOQExtraction:
    """Return a new BOQExtraction with all recorded corrections applied.

    Corrected totals are rolled up into lot/contract totals as a *delta*
    against the original item value, not by re-summing every item from
    scratch — that preserves whatever the original total-computation
    method was (a bidder's own printed Excel summary-sheet cell, or a
    sum of parsed PDF/OCR rows) and only nudges it by the size of the fix.
    """
    overrides = _corrections.get(bidder)
    if not overrides:
        return ext

    # A data-gap skeleton starts every total at None ("nothing entered
    # yet"), not at a real (if incomplete) figure — so once a reviewer
    # starts manually filling it in, totals need to accumulate from zero
    # rather than staying None forever (None + delta is still None).
    is_gap_skeleton = ext.data_gap is not None

    new_lots = []
    for lot in ext.lots:
        lot_delta_cif = 0.0
        lot_delta_erection = 0.0
        lot_delta_total = 0.0
        lot_changed = False
        new_sheets = []
        for sheet in lot.sheets:
            sheet_changed = False
            new_items = []
            for item in sheet.items:
                record = overrides.get((lot.lot_number, sheet.name, item.item_no))
                if record is None:
                    new_items.append(item)
                    continue

                old_cif = item.cif_total or 0.0
                old_erection = item.erection_total or 0.0
                old_total = item.total or 0.0

                updated = dataclasses.replace(
                    item, **record["fields"], is_corrected=True, is_missing=False
                )

                # If the reviewer only touched CIF/erection, re-derive the
                # combined total rather than leaving it stale.
                if "total" not in record["fields"] and (
                    "cif_total" in record["fields"] or "erection_total" in record["fields"]
                ):
                    if updated.cif_total is not None or updated.erection_total is not None:
                        updated = dataclasses.replace(
                            updated,
                            total=(updated.cif_total or 0.0) + (updated.erection_total or 0.0),
                        )

                lot_delta_cif += (updated.cif_total or 0.0) - old_cif
                lot_delta_erection += (updated.erection_total or 0.0) - old_erection
                lot_delta_total += (updated.total or 0.0) - old_total
                sheet_changed = True
                lot_changed = True
                new_items.append(updated)

            new_sheets.append(
                dataclasses.replace(sheet, items=tuple(new_items)) if sheet_changed else sheet
            )

        if lot_changed:
            base_cif = 0.0 if is_gap_skeleton else lot.total_cif
            base_erection = 0.0 if is_gap_skeleton else lot.total_erection
            base_price = 0.0 if is_gap_skeleton else lot.total_price
            lot = dataclasses.replace(
                lot,
                sheets=tuple(new_sheets),
                total_cif=None if base_cif is None else base_cif + lot_delta_cif,
                total_erection=None if base_erection is None else base_erection + lot_delta_erection,
                total_price=None if base_price is None else base_price + lot_delta_total,
            )
        new_lots.append(lot)

    new_lots = tuple(new_lots)
    base_contract_price = 0.0 if is_gap_skeleton else ext.total_contract_price
    total_contract_price = ext.total_contract_price
    if base_contract_price is not None:
        contract_delta = sum(
            (nl.total_price or 0.0) - (ol.total_price or 0.0)
            for nl, ol in zip(new_lots, ext.lots)
        )
        total_contract_price = base_contract_price + contract_delta

    return dataclasses.replace(ext, lots=new_lots, total_contract_price=total_contract_price)
