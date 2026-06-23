"""Content-hash based cache for expensive extraction results (Azure OCR).

Cache key = SHA-256 of file content, so identical files always hit cache
regardless of path. Results stored as JSON in .cache/ directory.
"""

import hashlib
import json
import logging
from pathlib import Path

from .excel_parser import BOQItem, BOQLot, BOQSheet

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent.parent / ".cache" / "extractions"


def _file_hash(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(filepath: Path) -> Path:
    return CACHE_DIR / f"{_file_hash(filepath)}.json"


def _lot_to_dict(lot: BOQLot) -> dict:
    return {
        "lot_name": lot.lot_name,
        "lot_number": lot.lot_number,
        "total_cif": lot.total_cif,
        "total_erection": lot.total_erection,
        "total_price": lot.total_price,
        "sheets": [
            {
                "name": sheet.name,
                "items": [
                    {
                        "item_no": item.item_no,
                        "description": item.description,
                        "unit": item.unit,
                        "qty": item.qty,
                        "cif_unit_rate": item.cif_unit_rate,
                        "cif_total": item.cif_total,
                        "erection_unit_rate": item.erection_unit_rate,
                        "erection_total": item.erection_total,
                        "total": item.total,
                        "is_section_header": item.is_section_header,
                        "raw_cif": item.raw_cif,
                        "raw_erection": item.raw_erection,
                    }
                    for item in sheet.items
                ],
            }
            for sheet in lot.sheets
        ],
    }


def _dict_to_lot(d: dict) -> BOQLot:
    sheets = tuple(
        BOQSheet(
            name=s["name"],
            items=tuple(
                BOQItem(
                    item_no=i["item_no"],
                    description=i["description"],
                    unit=i.get("unit"),
                    qty=i.get("qty"),
                    cif_unit_rate=i.get("cif_unit_rate"),
                    cif_total=i.get("cif_total"),
                    erection_unit_rate=i.get("erection_unit_rate"),
                    erection_total=i.get("erection_total"),
                    total=i.get("total"),
                    is_section_header=i.get("is_section_header", False),
                    raw_cif=i.get("raw_cif"),
                    raw_erection=i.get("raw_erection"),
                )
                for i in s["items"]
            ),
        )
        for s in d["sheets"]
    )
    return BOQLot(
        lot_name=d["lot_name"],
        lot_number=d["lot_number"],
        sheets=sheets,
        total_cif=d.get("total_cif"),
        total_erection=d.get("total_erection"),
        total_price=d.get("total_price"),
    )


def load_cached(filepath: Path) -> list[BOQLot] | None:
    """Load cached extraction results for a file. Returns None on cache miss."""
    cp = _cache_path(filepath)
    if not cp.exists():
        return None
    try:
        data = json.loads(cp.read_text())
        lots = [_dict_to_lot(d) for d in data["lots"]]
        logger.info("Cache hit for %s (%d lots)", filepath.name, len(lots))
        return lots
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Cache corrupt for %s: %s", filepath.name, e)
        cp.unlink(missing_ok=True)
        return None


def save_cached(filepath: Path, lots: list[BOQLot]) -> None:
    """Save extraction results to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp = _cache_path(filepath)
    data = {"source_file": filepath.name, "lots": [_lot_to_dict(lot) for lot in lots]}
    cp.write_text(json.dumps(data, indent=2))
    logger.info("Cached %d lots for %s", len(lots), filepath.name)
