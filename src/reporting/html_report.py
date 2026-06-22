from __future__ import annotations

from pathlib import Path

from src.analysis.comparator import build_tender_summary, compare_lot
from src.analysis.round_tracker import TenderRoundSummary
from src.models import Finding, FindingCategory, Severity, TenderData


def generate_html_report(
    tender: TenderData,
    round_name: str,
    round_summary: TenderRoundSummary,
    output_path: Path,
) -> Path:
    """Generate an interactive HTML report."""
    html = _build_html(tender, round_name, round_summary)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _build_html(
    tender: TenderData,
    round_name: str,
    round_summary: TenderRoundSummary,
) -> str:
    summary = build_tender_summary(tender, round_name)
    bidders = tender.bidders
    lots = tender.lots
    findings = tender.findings

    # Count findings by severity
    high_count = sum(1 for f in findings if f.severity == Severity.HIGH)
    medium_count = sum(1 for f in findings if f.severity == Severity.MEDIUM)
    low_count = sum(1 for f in findings if f.severity == Severity.LOW)

    # Build bidder totals
    bidder_totals: list[tuple[str, float]] = []
    for bidder in bidders:
        total = sum(v for v in summary.get(bidder, {}).values() if v is not None)
        bidder_totals.append((bidder, total))
    bidder_totals.sort(key=lambda x: x[1] if x[1] > 0 else float("inf"))

    summary_table_html = _build_summary_table(bidders, lots, summary, bidder_totals)
    findings_html = _build_findings_html(findings)
    lot_details_html = _build_lot_details(tender, round_name)
    round_movement_html = _build_round_movement(round_summary, tender.rounds)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bid Analysis — {tender.tender_id}</title>
<style>
{_get_css()}
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>Bid Analysis Report</h1>
        <div class="tender-info">
            <span class="tender-id">{tender.tender_id}</span>
            <span class="round-badge">{round_name}</span>
            <span class="bidder-count">{len(bidders)} Bidders</span>
        </div>
    </header>

    <section class="stats-bar">
        <div class="stat">
            <div class="stat-value">{len(bidders)}</div>
            <div class="stat-label">Bidders</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(lots)}</div>
            <div class="stat-label">Lots</div>
        </div>
        <div class="stat">
            <div class="stat-value finding-high">{high_count}</div>
            <div class="stat-label">High Findings</div>
        </div>
        <div class="stat">
            <div class="stat-value finding-medium">{medium_count}</div>
            <div class="stat-label">Medium Findings</div>
        </div>
        <div class="stat">
            <div class="stat-value">{low_count}</div>
            <div class="stat-label">Low Findings</div>
        </div>
    </section>

    <section>
        <h2>Bid Summary</h2>
        {summary_table_html}
    </section>

    <section>
        <h2>Price Movement Across Rounds</h2>
        {round_movement_html}
    </section>

    <section>
        <h2>Findings</h2>
        {findings_html}
    </section>

    <section>
        <h2>Lot Details</h2>
        {lot_details_html}
    </section>
</div>

<script>
{_get_js()}
</script>
</body>
</html>"""


def _build_summary_table(
    bidders: list[str],
    lots: list[str],
    summary: dict[str, dict[str, float | None]],
    bidder_totals: list[tuple[str, float]],
) -> str:
    rows = ""
    lowest_bidder = bidder_totals[0][0] if bidder_totals else None

    for rank, (bidder, total) in enumerate(bidder_totals, 1):
        lot_cells = ""
        for lot in lots:
            val = summary.get(bidder, {}).get(lot)
            lot_cells += f'<td class="num">{_fmt(val)}</td>'

        row_class = "best-row" if bidder == lowest_bidder and total > 0 else ""
        rows += f"""<tr class="{row_class}">
            <td>{rank}</td>
            <td class="bidder-name">{bidder}</td>
            {lot_cells}
            <td class="num total-cell">{_fmt(total)}</td>
        </tr>"""

    lot_headers = "".join(f"<th>{lot}</th>" for lot in lots)

    return f"""<div class="table-wrapper">
    <table class="summary-table">
        <thead>
            <tr>
                <th>Rank</th>
                <th>Bidder</th>
                {lot_headers}
                <th>Contract Total (AED)</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    </div>"""


def _build_findings_html(findings: list[Finding]) -> str:
    if not findings:
        return "<p>No findings detected.</p>"

    # Group by category
    by_category: dict[str, list[Finding]] = {}
    for f in findings:
        cat = f.category.value
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(f)

    html = '<div class="findings-grid">'
    for category, items in sorted(by_category.items()):
        category_label = category.replace("_", " ").title()
        items_html = ""
        for f in sorted(items, key=lambda x: (x.severity.value, x.bidder)):
            sev_class = f"severity-{f.severity.value}"
            items_html += f"""<div class="finding-item {sev_class}">
                <span class="finding-badge">{f.severity.value.upper()}</span>
                <strong>{f.bidder}</strong> — {f.lot}
                {f' (Item {f.item_no})' if f.item_no else ''}
                <p>{f.message}</p>
            </div>"""

        html += f"""<div class="finding-category">
            <h3>{category_label} ({len(items)})</h3>
            {items_html}
        </div>"""

    html += "</div>"
    return html


def _build_lot_details(tender: TenderData, round_name: str) -> str:
    html = ""
    for lot in tender.lots:
        comparison = compare_lot(tender, lot, round_name)
        html += f"""<details class="lot-detail">
            <summary><strong>{lot}</strong> — {len(comparison.bidders)} bidders</summary>
            <div class="lot-content">"""

        for section in comparison.sections:
            html += f"<h4>{section.section_name}</h4>"
            html += '<div class="table-wrapper"><table class="detail-table"><thead><tr>'
            html += "<th>Item</th><th>Description</th><th>Unit</th><th>Qty</th>"

            for bidder in comparison.bidders:
                html += f'<th class="bidder-col">{bidder}<br>Total (AED)</th>'
            html += "<th>Median</th></tr></thead><tbody>"

            for item in section.items:
                html += "<tr>"
                html += f"<td>{item.item_no}</td>"
                desc_short = item.description[:60] + ("..." if len(item.description) > 60 else "")
                html += f'<td class="desc-cell" title="{_escape(item.description)}">{_escape(desc_short)}</td>'
                html += f"<td>{item.unit or ''}</td>"
                html += f'<td class="num">{_fmt_qty(item.qty)}</td>'

                min_price = item.min_total
                for bidder in comparison.bidders:
                    total = item.bidder_total_price.get(bidder)
                    cell_class = "num"
                    if total is not None and min_price is not None and total == min_price:
                        cell_class += " best-price"
                    elif total is None:
                        cell_class += " unquoted"
                    html += f'<td class="{cell_class}">{_fmt(total)}</td>'

                html += f'<td class="num median-cell">{_fmt(item.median_total)}</td>'
                html += "</tr>"

            html += "</tbody></table></div>"

        html += "</div></details>"
    return html


def _build_round_movement(
    round_summary: TenderRoundSummary,
    rounds: list[str],
) -> str:
    if not round_summary.movements:
        return "<p>No multi-round data available.</p>"

    html = '<div class="table-wrapper"><table class="detail-table"><thead><tr>'
    html += "<th>Bidder</th><th>Lot</th>"
    for r in rounds:
        html += f"<th>{r}</th>"
    html += "<th>Change</th></tr></thead><tbody>"

    for m in round_summary.movements:
        if len(m.round_totals) < 2:
            continue
        html += f"<tr><td>{m.bidder}</td><td>{m.lot}</td>"
        for r in rounds:
            val = m.round_totals.get(r)
            html += f'<td class="num">{_fmt(val)}</td>'

        pct = m.total_change_pct
        if pct is not None:
            pct_class = "positive" if pct > 0 else "negative"
            html += f'<td class="num {pct_class}">{pct:+.1f}%</td>'
        else:
            html += "<td>—</td>"
        html += "</tr>"

    html += "</tbody></table></div>"
    return html


def _fmt(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:,.0f}"


def _fmt_qty(val: float | None) -> str:
    if val is None:
        return "—"
    if val == int(val):
        return str(int(val))
    return f"{val:,.2f}"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _get_css() -> str:
    return """
:root {
    --primary: #1F4E79;
    --primary-light: #D6E4F0;
    --success: #27AE60;
    --warning: #F39C12;
    --danger: #E74C3C;
    --bg: #F8F9FA;
    --card-bg: #FFFFFF;
    --text: #2C3E50;
    --border: #DEE2E6;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }
.container { max-width: 1400px; margin: 0 auto; padding: 20px; }

header { background: var(--primary); color: white; padding: 24px 32px; border-radius: 12px; margin-bottom: 24px; }
header h1 { font-size: 24px; margin-bottom: 8px; }
.tender-info { display: flex; gap: 12px; align-items: center; }
.tender-id { background: rgba(255,255,255,0.2); padding: 4px 12px; border-radius: 6px; font-weight: 600; }
.round-badge { background: var(--success); padding: 4px 12px; border-radius: 6px; }
.bidder-count { opacity: 0.8; }

.stats-bar { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.stat { background: var(--card-bg); padding: 16px 24px; border-radius: 8px; text-align: center; flex: 1; min-width: 120px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.stat-value { font-size: 28px; font-weight: 700; color: var(--primary); }
.stat-label { font-size: 12px; color: #6C757D; text-transform: uppercase; letter-spacing: 0.5px; }
.finding-high { color: var(--danger) !important; }
.finding-medium { color: var(--warning) !important; }

section { background: var(--card-bg); padding: 24px; border-radius: 8px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
section h2 { color: var(--primary); margin-bottom: 16px; font-size: 18px; }

.table-wrapper { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: var(--primary); color: white; padding: 10px 8px; text-align: left; position: sticky; top: 0; white-space: nowrap; }
td { padding: 8px; border-bottom: 1px solid var(--border); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.total-cell { font-weight: 700; }
.best-row { background: #E8F5E9; }
.best-price { background: #C8E6C9; font-weight: 600; }
.unquoted { background: #FFF3CD; }
.bidder-col { min-width: 100px; }
.desc-cell { max-width: 250px; overflow: hidden; text-overflow: ellipsis; }
.median-cell { font-style: italic; color: #6C757D; }
.positive { color: var(--danger); }
.negative { color: var(--success); }

.summary-table .bidder-name { font-weight: 600; }

.findings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 16px; }
.finding-category h3 { color: var(--primary); margin-bottom: 8px; font-size: 14px; }
.finding-item { padding: 10px; border-radius: 6px; margin-bottom: 8px; font-size: 13px; border-left: 4px solid var(--border); }
.finding-item p { margin-top: 4px; color: #6C757D; font-size: 12px; }
.finding-badge { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 700; margin-right: 6px; }
.severity-high { border-left-color: var(--danger); background: #FDF0EF; }
.severity-high .finding-badge { background: var(--danger); color: white; }
.severity-medium { border-left-color: var(--warning); background: #FEF9E7; }
.severity-medium .finding-badge { background: var(--warning); color: white; }
.severity-low { border-left-color: #17A2B8; background: #EBF5FB; }
.severity-low .finding-badge { background: #17A2B8; color: white; }

details.lot-detail { margin-bottom: 12px; }
details.lot-detail summary { cursor: pointer; padding: 12px; background: var(--primary-light); border-radius: 6px; font-size: 14px; }
details.lot-detail summary:hover { background: #C2D6EA; }
.lot-content { padding: 16px 0; }
.lot-content h4 { color: var(--primary); margin: 16px 0 8px; }
"""


def _get_js() -> str:
    return """
// Simple table sort
document.querySelectorAll('th').forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
        const table = th.closest('table');
        const tbody = table.querySelector('tbody');
        if (!tbody) return;
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const idx = Array.from(th.parentNode.children).indexOf(th);
        const asc = th.dataset.sort !== 'asc';
        th.dataset.sort = asc ? 'asc' : 'desc';
        rows.sort((a, b) => {
            const aVal = a.children[idx]?.textContent.replace(/,/g, '').trim() || '';
            const bVal = b.children[idx]?.textContent.replace(/,/g, '').trim() || '';
            const aNum = parseFloat(aVal);
            const bNum = parseFloat(bVal);
            if (!isNaN(aNum) && !isNaN(bNum)) return asc ? aNum - bNum : bNum - aNum;
            return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
        });
        rows.forEach(row => tbody.appendChild(row));
    });
});
"""
