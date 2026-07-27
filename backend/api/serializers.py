"""Convert dataclass models to JSON-serializable dicts for the API."""

from ..extraction.excel_parser import BOQExtraction, BOQItem, BOQLot, BOQSheet
from ..analysis.comparator import ComparisonResult, ComparisonItem, LotComparison, Flag
from ..analysis.rounds import BidderRoundTrend, RoundPoint, RoundTrendResult


def serialize_item(item: BOQItem) -> dict:
    return {
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
        "is_corrected": item.is_corrected,
        "is_missing": item.is_missing,
    }


def serialize_sheet(sheet: BOQSheet) -> dict:
    return {
        "name": sheet.name,
        "items": [serialize_item(i) for i in sheet.items],
        "item_count": len([i for i in sheet.items if not i.is_section_header]),
    }


def serialize_lot(lot: BOQLot) -> dict:
    return {
        "lot_name": lot.lot_name,
        "lot_number": lot.lot_number,
        "sheets": [serialize_sheet(s) for s in lot.sheets],
        "total_cif": lot.total_cif,
        "total_erection": lot.total_erection,
        "total_price": lot.total_price,
        "total_items": sum(
            len([i for i in s.items if not i.is_section_header])
            for s in lot.sheets
        ),
    }


def serialize_extraction(ext: BOQExtraction) -> dict:
    return {
        "tender_no": ext.tender_no,
        "bidder": ext.bidder,
        "round_name": ext.round_name,
        "lots": [serialize_lot(l) for l in ext.lots],
        "total_contract_price": ext.total_contract_price,
        "data_gap": ext.data_gap,
    }


def serialize_flag(flag: Flag) -> dict:
    return {
        "severity": flag.severity,
        "category": flag.category,
        "bidder": flag.bidder,
        "lot": flag.lot,
        "item_no": flag.item_no,
        "description": flag.description,
        "detail": flag.detail,
    }


def serialize_comparison_item(item: ComparisonItem) -> dict:
    return {
        "item_no": item.item_no,
        "description": item.description,
        "unit": item.unit,
        "qty": item.qty,
        "bidder_prices": item.bidder_prices,
        "match_method": item.match_method,
        "match_confidence": item.match_confidence,
    }


def serialize_lot_comparison(lc: LotComparison) -> dict:
    return {
        "lot_name": lc.lot_name,
        "lot_number": lc.lot_number,
        "items": [serialize_comparison_item(i) for i in lc.items],
        "bidder_totals": lc.bidder_totals,
        "item_count": len(lc.items),
    }


def serialize_round_point(point: RoundPoint) -> dict:
    return {
        "round_name": point.round_name,
        "total_contract_price": point.total_contract_price,
        "lot_totals": point.lot_totals,
    }


def serialize_bidder_round_trend(trend: BidderRoundTrend) -> dict:
    return {
        "bidder": trend.bidder,
        "points": [serialize_round_point(p) for p in trend.points],
    }


def serialize_round_trend(result: RoundTrendResult) -> dict:
    return {
        "rounds_present": list(result.rounds_present),
        "bidders": [serialize_bidder_round_trend(b) for b in result.bidders],
        "flags": [serialize_flag(f) for f in result.flags],
    }


def serialize_comparison(result: ComparisonResult) -> dict:
    return {
        "tender_no": result.tender_no,
        "round_name": result.round_name,
        "lots": [serialize_lot_comparison(l) for l in result.lots],
        "flags": [serialize_flag(f) for f in result.flags],
        "bidder_grand_totals": result.bidder_grand_totals,
        "flag_summary": {
            "critical": len([f for f in result.flags if f.severity == "critical"]),
            "warning": len([f for f in result.flags if f.severity == "warning"]),
            "info": len([f for f in result.flags if f.severity == "info"]),
        },
    }
