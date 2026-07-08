"""Self-contained HTML export of a recommendation report.

Structure/CSS borrowed for visual consistency from the frozen
`src/reporting/html_report.py` reference (stats bar, findings-by-severity
styling) but rewritten from scratch against this backend's actual
`ComparisonResult`/`Flag` dataclasses — the reference module's data model
(`TenderData`, `Finding`) is incompatible and can't be imported.
"""

import html as html_lib

from ..analysis.comparator import ComparisonResult
from .digest import build_report_digest

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
SEVERITY_LABEL = {"critical": "Critical", "warning": "Warning", "info": "Info"}


def _esc(value) -> str:
    return html_lib.escape(str(value)) if value is not None else ""


def _get_css() -> str:
    return """
body { font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; background: #f4f6f8; color: #1a2733; margin: 0; padding: 2rem; }
.container { max-width: 1100px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
.meta { color: #64748b; margin-bottom: 1.5rem; }
.card { background: #fff; border-radius: 10px; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.card h2 { font-size: 1.05rem; margin-top: 0; }
.badge { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600; }
.badge-award { background: #d1fae5; color: #065f46; }
.badge-shortlist { background: #dbeafe; color: #1e40af; margin-right: 0.4rem; }
.badge-gap { background: #fef3c7; color: #92400e; }
table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
th, td { text-align: left; padding: 0.5rem 0.65rem; border-bottom: 1px solid #e5e7eb; font-size: 0.9rem; vertical-align: top; }
th { background: #1F4E79; color: #fff; }
tr.best td { background: #ecfdf5; }
tr.gap td { color: #94a3b8; font-style: italic; }
.sev-critical { background: #fee2e2; }
.sev-warning { background: #fef9c3; }
.sev-info { background: #e0f2fe; }
ul.caveats { padding-left: 1.2rem; color: #92400e; }
.bidder-note { border-left: 3px solid #1F4E79; padding-left: 0.9rem; margin-bottom: 1rem; }
.bidder-note.gap { border-left-color: #d1a34a; opacity: 0.75; }
.bidder-note h3 { margin: 0 0 0.25rem 0; font-size: 0.95rem; }
"""


def _bid_summary_table(result: ComparisonResult, data_gap_bidders: set[str]) -> str:
    eligible = sorted(
        (
            (b, t) for b, t in result.bidder_grand_totals.items()
            if t is not None and b not in data_gap_bidders
        ),
        key=lambda bt: bt[1],
    )
    best_bidder = eligible[0][0] if eligible else None
    rank_by_bidder = {b: i + 1 for i, (b, _) in enumerate(eligible)}

    rows = []
    for bidder in sorted(result.bidder_grand_totals, key=lambda b: rank_by_bidder.get(b, 999)):
        total = result.bidder_grand_totals.get(bidder)
        is_gap = bidder in data_gap_bidders
        row_class = "best" if bidder == best_bidder else ("gap" if is_gap else "")
        total_display = f"{total:,.0f}" if total is not None else "—"
        rank_display = rank_by_bidder.get(bidder, "—")
        rows.append(
            f'<tr class="{row_class}"><td>{_esc(bidder)}</td>'
            f'<td>{total_display}</td><td>{rank_display}</td></tr>'
        )
    return (
        "<table><thead><tr><th>Bidder</th><th>Contract Total</th>"
        f"<th>Rank</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _bidder_notes_html(report: dict) -> str:
    blocks = []
    for bidder, note in report.get("bidder_notes", {}).items():
        is_gap = note.get("position") == "excluded_data_gap"
        points = "".join(f"<li>{_esc(p)}</li>" for p in note.get("negotiation_points", []))
        flags = "".join(f"<li>{_esc(f)}</li>" for f in note.get("flags_highlighted", []))
        blocks.append(f"""
<div class="bidder-note {'gap' if is_gap else ''}">
  <h3>{_esc(bidder)} <span class="badge {'badge-gap' if is_gap else ''}">{_esc(note.get('position', ''))}</span></h3>
  <p>{_esc(note.get('summary', ''))}</p>
  {f'<ul>{points}</ul>' if points else ''}
  {f'<p><strong>Flags:</strong></p><ul>{flags}</ul>' if flags else ''}
</div>""")
    return "".join(blocks)


def _flags_table(top_flags: dict[str, list[dict]]) -> str:
    """Same curated top-N-per-bidder flags the LLM digest saw (see
    digest.py::_top_flags), not the full pairwise-outlier flag list — that
    runs into the thousands and produces a multi-megabyte, unreadable page
    with no relationship to what the narrative above actually references."""
    rows = []
    for bidder, flags in top_flags.items():
        for flag in sorted(flags, key=lambda f: SEVERITY_ORDER.get(f["severity"], 9)):
            rows.append(
                f'<tr class="sev-{_esc(flag["severity"])}"><td>{_esc(bidder)}</td>'
                f'<td>{SEVERITY_LABEL.get(flag["severity"], flag["severity"])}</td>'
                f'<td>{_esc(flag["category"])}</td>'
                f'<td>{_esc(flag["lot"])}</td><td>{_esc(flag["item_no"])}</td>'
                f'<td>{_esc(flag["description"])}</td><td>{_esc(flag["detail"])}</td></tr>'
            )
    return (
        "<table><thead><tr><th>Bidder</th><th>Severity</th><th>Category</th>"
        "<th>Lot</th><th>Item</th><th>Description</th><th>Detail</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def build_html_report(result: ComparisonResult, report: dict) -> str:
    data_gap_bidders = {
        b for b, n in report.get("bidder_notes", {}).items()
        if n.get("position") == "excluded_data_gap"
    }
    rec = report.get("recommendation", {})
    shortlist_badges = "".join(
        f'<span class="badge badge-shortlist">{_esc(b)}</span>' for b in rec.get("shortlist", [])
    )
    caveats = "".join(f"<li>{_esc(c)}</li>" for c in report.get("caveats", []))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Recommendation Report — {_esc(result.tender_no)}</title>
<style>{_get_css()}</style>
</head>
<body>
<div class="container">
  <h1>Bid Recommendation Report</h1>
  <div class="meta">Tender {_esc(result.tender_no)} · Round: {_esc(result.round_name)}</div>

  <div class="card">
    <h2>Executive Summary</h2>
    <p>{_esc(report.get('executive_summary', ''))}</p>
  </div>

  <div class="card">
    <h2>Recommendation</h2>
    <p><span class="badge badge-award">{_esc(rec.get('primary_award') or 'No clear recommendation')}</span></p>
    <p>{shortlist_badges}</p>
    <p>{_esc(rec.get('reasoning', ''))}</p>
    {f'<ul class="caveats">{caveats}</ul>' if caveats else ''}
  </div>

  <div class="card">
    <h2>Bid Summary</h2>
    {_bid_summary_table(result, data_gap_bidders)}
  </div>

  <div class="card">
    <h2>Bidder Negotiation Notes</h2>
    {_bidder_notes_html(report)}
  </div>

  <div class="card">
    <h2>Flags</h2>
    {_flags_table(build_report_digest(result)["top_flags"])}
  </div>
</div>
</body>
</html>"""
