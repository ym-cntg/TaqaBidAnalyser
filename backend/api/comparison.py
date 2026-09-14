"""GET /api/rfqs/{rfqnum}/comparison -- side-by-side bidder pricing per
BOQ line, plus automated commercial flags. Supports an optional ?round=
query param (see backend/api/round_snapshots.py) to view the same grid at
any later negotiation revision, not just the original quote.

Vendor names resolved via `companies` (companies.company =
rfqvendor.VENDOR) -- first use of this table in this codebase; its
fully-qualified name is assumed to match the rest of the schema and is
UNVERIFIED against a real deployment.

Manual price corrections (backend/api/corrections.py,
bid_analyzer_price_corrections) are overlaid on top of the raw
quotationline data here at display time -- never written back into
quotationline itself. Corrections are trusted: a corrected cell is
excluded from arithmetic_error/outlier/zero_price flagging (it's already
been reviewed by a person) but still fully participates in is_lowest and
contract_total, since that's the point of correcting it. A correction
fixes a specific bad ORIGINAL-round entry and doesn't carry a round of
its own, so it's only applied when viewing the original round -- reusing
the same absolute price at every later round would misrepresent whatever
negotiated discount happened after the correction was made.

Technical disqualification (QL2 = "TNA"): a real stakeholder ask --
technically-rejected line items must never factor into commercial
evaluation. quotationline/altquotationline carry a QL2 status column
confirmed as a real technical-acceptance field (see
databricks/FINDINGS.md), with "TNA" ("Technically Not Accepted") as the
one value treated as disqualifying here, per an explicit product
decision -- Cancel/CNA/NOQUOTE are left as-is. **Caveat, built anyway per
an explicit decision to not block on verifying it first**: QL2's value
distribution was only confirmed on altquotationline (a smaller,
non-construction sample) -- whether it's populated the same way on
quotationline for a real detailed BOQ is unverified. _fetch_technical_status()
is deliberately fail-open (same pattern as _fetch_corrections): if QL2
doesn't exist or the query fails for any other reason, technical
disqualification is simply never applied rather than breaking the whole
comparison view. A disqualified cell is excluded from is_lowest,
contract_total, the outlier baseline, and every other flag -- but still
shown (not hidden like a corrected-away value), clearly marked, so the
analyst can see why a real submitted price isn't in commercial play.

Manual disqualification (backend/api/disqualifications.py,
bid_analyzer_line_disqualifications) lets an analyst disqualify a line
the same way, for a reason QL2 doesn't capture -- also never written
back into quotationline, applied as a display-time overlay here exactly
like corrections. It's deliberately **add-only relative to Maximo**: the
two sources are merged with `or` (technically_disqualified = QL2-driven
OR manual), so an analyst can undo their own manual entry but can never
flip a real QL2='TNA' rejection back to qualified -- there's no special-
case code enforcing that rule, it falls straight out of the OR.

Partial bids (backend/api/partial_bids.py, bid_analyzer_partial_bids): an
analyst can flag a vendor's entire bid on this RFQ as a deliberate
partial-scope submission (e.g. they only bid one lot of a multi-lot
tender) -- a whole-vendor concept, unlike disqualification, so it's keyed
on (rfqnum, vendor) with no rfqlinenum. Never written back into Maximo,
applied as a display-time overlay exactly like the other overlays, and
fetched unconditionally regardless of round (a vendor's bid scope doesn't
change round to round). Marking a vendor partial changes three things
about how they're compared, per an explicit product decision: their
unquoted_count is suppressed to 0 (an unquoted line is expected for a
partial bidder, not a red flag), quoted_line_count is exposed so the
frontend can show how much of the BOQ their contract_total actually
covers, and is_partial_bid lets the frontend exclude them from the
vendor-summary "Lowest total" badge (comparing a partial-scope total
against a full-scope one is apples-to-oranges) -- they can still win
individual lines/split-award on whatever they did bid, since that part of
the math is unaffected.

Round-scoped view: DISCOUNTHISTORYLINE only carries a post-discount
LINECOST (LINECOSTWDIS), no per-round unit rate, so a round other than
"original" derives unit_cost = line_cost / qty (qty doesn't change
across rounds -- these are price renegotiations, not scope changes).
Because that unit_cost is derived, not independently reported, the
arithmetic_error check (which exists to catch a vendor's own qty x rate
math not matching what they typed) is only meaningful for the original
round and is always False for any other round.

Pure read of quotationline/DISCOUNTHISTORY(LINE)/rfqvendor/companies --
no Unity Catalog write grant needed for the comparison itself,
independent of the Projects feature's write-blocked status. The
corrections *overlay* fetch is a read too; only backend/api/corrections.py
writes.
"""

import statistics
from dataclasses import asdict, dataclass

from fastapi import APIRouter, HTTPException

from backend.api.round_snapshots import ORIGINAL, build_round_snapshots
from backend.db import CATALOG, SCHEMA, escape_sql_literal, get_connection

router = APIRouter()

LINES_CAP = 500
ARITHMETIC_TOLERANCE = 0.01
OUTLIER_MIN_QUOTES = 3
# A vendor needs at least this many peer-comparable lines before we trust
# a "typical ratio to the peer group" for them -- see the outlier note in
# build_comparison() below for why this replaced a flat peer-deviation
# check. First-pass value, tune later against real data.
MIN_LINES_FOR_VENDOR_BASELINE = 5
# Z-score threshold against a vendor's own historical ratio-to-peer-median
# distribution -- stricter than the flat 50%-deviation check this
# replaced, and only ever the single most extreme line per vendor's
# distribution can cross it before also losing to another vendor's
# stronger deviation on the same line (see the "at most one outlier per
# line" cap below).
OUTLIER_Z_THRESHOLD = 3.0
# A floor on a vendor's own historical MAD (median absolute deviation),
# expressed as a fraction of their baseline ratio. Without this, a
# vendor whose historical ratio-to-peer-median happens to be extremely
# tight (or, in a small sample, more than half identical) would see even
# a trivial, insignificant wobble -- e.g. the peer median itself shifting
# slightly because a *different* vendor spiked on that line -- divided by
# a near-zero MAD and treated as infinitely anomalous. 3% is a first-pass
# value: small enough to still catch a real anomaly, large enough that
# ordinary noise doesn't get amplified into a false positive.
MAD_FLOOR_FRACTION = 0.03
# QL2 values treated as a technical disqualification -- see the module
# docstring for the real-data caveat and why only "TNA" is included.
DISQUALIFYING_QL2_VALUES = {"TNA"}


@dataclass
class LinePrice:
    unit_cost: float | None
    line_cost: float | None
    unquoted: bool
    is_lowest: bool
    arithmetic_error: bool
    outlier: bool
    zero_price: bool
    technically_disqualified: bool
    disqualification_source: str | None
    disqualification_reason: str | None
    disqualified_by_label: str | None
    corrected: bool
    corrected_by_label: str | None
    corrected_note: str | None
    corrected_at: str | None


@dataclass
class ComparisonLine:
    rfqlinenum: float
    description: str | None
    qty: float | None
    unit: str | None
    prices: dict[str, LinePrice]


@dataclass
class VendorSummary:
    vendor: str
    name: str | None
    contract_total: float
    unquoted_count: int
    arithmetic_error_count: int
    outlier_count: int
    zero_price_count: int
    technically_disqualified_count: int
    is_partial_bid: bool
    quoted_line_count: int
    partial_bid_note: str | None


@dataclass
class NotSubmittedVendor:
    vendor: str
    name: str | None


@dataclass
class SplitAwardTotal:
    vendor: str
    name: str | None
    total: float
    line_count: int


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


def _fetch_vendor_roster(rfqnum: str) -> dict[str, str | None]:
    """Invited vendors for this RFQ -> resolved company name (None if
    unresolved). rfqvendor, not quotationline, is the source of truth for
    "invited" -- quotationline only shows who actually priced something."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT DISTINCT rv.VENDOR, c.name
                    FROM {CATALOG}.{SCHEMA}.rfqvendor rv
                    LEFT JOIN {CATALOG}.{SCHEMA}.companies c ON c.company = rv.VENDOR
                    WHERE rv.RFQNUM = '{escape_sql_literal(rfqnum)}'
                    """
                )
                return {row.VENDOR: row.name for row in cursor.fetchall()}
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Query against rfqvendor/companies failed: {exc}"
        ) from exc


def _fetch_quotationlines(rfqnum: str) -> list:
    # ORDERUNIT = 'HEADER' rows are non-priced section-break markers, not
    # real BOQ line items -- excluded from the comparison entirely.
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT RFQLINENUM, VENDOR, DESCRIPTION, ORDERQTY, ORDERUNIT, UNITCOST, LINECOST
                    FROM {CATALOG}.{SCHEMA}.quotationline
                    WHERE RFQNUM = '{escape_sql_literal(rfqnum)}'
                      AND (ORDERUNIT IS NULL OR ORDERUNIT <> 'HEADER')
                    """
                )
                return cursor.fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Query against quotationline failed: {exc}"
        ) from exc


def _fetch_corrections(rfqnum: str) -> dict[tuple[float, str], object]:
    """Latest correction per (rfqlinenum, vendor), or {} if the
    corrections table doesn't exist yet (nobody has corrected anything,
    or the write grant isn't applied). Deliberately swallowed here --
    the read-only comparison view must keep working regardless; a broken
    write path elsewhere shouldn't take down a working read path."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT rfqlinenum, vendor, unit_cost, note, corrected_by, corrected_at
                    FROM {CATALOG}.{SCHEMA}.bid_analyzer_price_corrections
                    WHERE rfqnum = '{escape_sql_literal(rfqnum)}'
                    ORDER BY corrected_at ASC
                    """
                )
                rows = cursor.fetchall()
    except Exception:
        return {}

    latest: dict[tuple[float, str], object] = {}
    for row in rows:
        latest[(row.rfqlinenum, row.vendor)] = row  # ASC order -> last write wins
    return latest


def _fetch_technical_status(rfqnum: str) -> dict[tuple[float, str], str | None]:
    """(rfqlinenum, vendor) -> QL2 status, or {} if the column doesn't
    exist here or the query fails for any other reason. Deliberately
    fail-open, same reasoning as _fetch_corrections: QL2's real-data
    behavior on quotationline (as opposed to altquotationline, where it
    was actually confirmed) is unverified -- see the module docstring.
    The read-only comparison view must keep working regardless; an
    unavailable technical-status column shouldn't take down a working
    read path, it should just mean disqualification isn't applied."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT RFQLINENUM, VENDOR, QL2
                    FROM {CATALOG}.{SCHEMA}.quotationline
                    WHERE RFQNUM = '{escape_sql_literal(rfqnum)}'
                    """
                )
                return {(row.RFQLINENUM, row.VENDOR): row.QL2 for row in cursor.fetchall()}
    except Exception:
        return {}


def _fetch_manual_disqualifications(rfqnum: str) -> dict[tuple[float, str], object]:
    """Latest manual disqualification entry per (rfqlinenum, vendor), or
    {} if the table doesn't exist yet (nobody has disqualified anything,
    or the write grant isn't applied). Deliberately fail-open, same
    reasoning as _fetch_corrections -- a read-only view must keep
    working regardless of an unrelated write-path gap. The latest row's
    `disqualified` boolean is the current state; a later disqualified=False
    row is how an analyst undoes their own earlier entry (see
    backend/api/disqualifications.py)."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT rfqlinenum, vendor, disqualified, reason, disqualified_by, disqualified_at
                    FROM {CATALOG}.{SCHEMA}.bid_analyzer_line_disqualifications
                    WHERE rfqnum = '{escape_sql_literal(rfqnum)}'
                    ORDER BY disqualified_at ASC
                    """
                )
                rows = cursor.fetchall()
    except Exception:
        return {}

    latest: dict[tuple[float, str], object] = {}
    for row in rows:
        latest[(row.rfqlinenum, row.vendor)] = row  # ASC order -> last write wins
    return latest


def _fetch_partial_bids(rfqnum: str) -> dict[str, object]:
    """Latest partial-bid flag per vendor, or {} if the table doesn't
    exist yet (nobody has flagged anything, or the write grant isn't
    applied). Deliberately fail-open, same reasoning as
    _fetch_manual_disqualifications. Whole-vendor, not per-line -- keyed
    on vendor alone, unlike the other two overlays."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT vendor, is_partial, note, marked_by, marked_at
                    FROM {CATALOG}.{SCHEMA}.bid_analyzer_partial_bids
                    WHERE rfqnum = '{escape_sql_literal(rfqnum)}'
                    ORDER BY marked_at ASC
                    """
                )
                rows = cursor.fetchall()
    except Exception:
        return {}

    latest: dict[str, object] = {}
    for row in rows:
        latest[row.vendor] = row  # ASC order -> last write wins
    return latest


def _fetch_user_names(user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    quoted = ", ".join(f"'{escape_sql_literal(u)}'" for u in user_ids)
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT user_id, display_name FROM {CATALOG}.{SCHEMA}.bid_analyzer_users "
                    f"WHERE user_id IN ({quoted})"
                )
                return {row.user_id: row.display_name for row in cursor.fetchall()}
    except Exception:
        return {}


def build_comparison(rfqnum: str, round_label: str | None = None) -> dict:
    """The comparison payload as a plain callable, so other modules (e.g.
    negotiation_report.py) can reuse it via an in-process call rather than
    an HTTP round trip to our own API.

    round_label picks which negotiation round to view: None/"original"
    (the default) uses quotationline's own UNITCOST/LINECOST directly.
    Any other value must be one of build_round_snapshots()'s
    rounds_present labels -- see the module docstring above for how a
    later round's prices are derived.
    """
    vendor_names = _fetch_vendor_roster(rfqnum)
    rows = _fetch_quotationlines(rfqnum)

    if not rows and not vendor_names:
        raise HTTPException(status_code=404, detail=f"Unknown RFQNUM {rfqnum!r}")

    round_data = build_round_snapshots(rfqnum)
    rounds_present = round_data["rounds_present"]
    selected_round = round_label or ORIGINAL
    if selected_round not in rounds_present:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown round {selected_round!r} for {rfqnum}. Valid rounds: {rounds_present}",
        )
    is_original = selected_round == ORIGINAL
    snapshots = round_data["snapshots"]

    corrections = _fetch_corrections(rfqnum) if is_original else {}
    # Technical/manual disqualification status doesn't change round to
    # round (it's locked before commercial negotiation even starts), so
    # both are fetched once and applied regardless of which round is
    # being viewed.
    technical_status = _fetch_technical_status(rfqnum)
    manual_disqualifications = _fetch_manual_disqualifications(rfqnum)
    # Bid scope (partial vs. full) is a property of the vendor's
    # submission, not a given negotiation round, so this is fetched
    # unconditionally too -- same reasoning as the two disqualification
    # overlays above.
    partial_bids = _fetch_partial_bids(rfqnum)
    user_names = _fetch_user_names(
        {c.corrected_by for c in corrections.values()}
        | {d.disqualified_by for d in manual_disqualifications.values()}
        | {p.marked_by for p in partial_bids.values()}
    )

    lines_by_num: dict[float, list] = {}
    for row in rows:
        lines_by_num.setdefault(row.RFQLINENUM, []).append(row)

    submitting_vendors = {row.VENDOR for row in rows}
    if not is_original:
        # Only vendors who actually have a forward-filled price by this
        # round -- almost always identical to the original round's set,
        # except a vendor who genuinely never submitted anything at all.
        submitting_vendors = {
            v for v in submitting_vendors if snapshots.get(v, {}).get(selected_round) is not None
        }

    # Pass 1: resolve (unit_cost, line_cost, qty, corrected) for every
    # (line, vendor) up front. Needed before any flagging, because outlier
    # detection (pass 2 below) has to see every vendor's full price
    # history across the whole BOQ before it can tell "unusual for this
    # vendor" apart from "this vendor is just generally pricier/cheaper".
    canonical_by_line: dict[float, object] = {}
    resolved_by_line: dict[float, dict[str, dict]] = {}
    for linenum, line_rows in lines_by_num.items():
        canonical = line_rows[0]
        canonical_by_line[linenum] = canonical
        by_vendor = {r.VENDOR: r for r in line_rows}
        canonical_qty = float(canonical.ORDERQTY) if canonical.ORDERQTY is not None else None

        resolved: dict[str, dict] = {}
        for vendor in submitting_vendors:
            if is_original:
                r = by_vendor.get(vendor)
                unit_cost = float(r.UNITCOST) if r is not None and r.UNITCOST is not None else None
                line_cost = float(r.LINECOST) if r is not None and r.LINECOST is not None else None
                qty = float(r.ORDERQTY) if r is not None and r.ORDERQTY is not None else None
            else:
                line_cost = snapshots.get(vendor, {}).get(selected_round, {}).get(linenum)
                qty = canonical_qty
                unit_cost = (line_cost / qty) if (line_cost is not None and qty) else None

            correction = corrections.get((linenum, vendor))
            corrected = correction is not None
            corrected_by_label = None
            corrected_note = None
            corrected_at = None
            if correction is not None:
                unit_cost = float(correction.unit_cost)
                line_cost = unit_cost * canonical_qty if canonical_qty is not None else None
                corrected_by_label = user_names.get(correction.corrected_by, correction.corrected_by)
                corrected_note = correction.note
                corrected_at = _iso(correction.corrected_at)

            # QL2-driven disqualification is Maximo's system-of-record
            # status; the manual overlay can only ADD to it or undo an
            # analyst's own earlier entry, never cancel a real QL2='TNA'
            # -- the `or` below is the entire enforcement of that rule.
            ql2_disqualified = technical_status.get((linenum, vendor)) in DISQUALIFYING_QL2_VALUES
            manual_entry = manual_disqualifications.get((linenum, vendor))
            manual_disqualified = manual_entry is not None and manual_entry.disqualified
            technically_disqualified = ql2_disqualified or manual_disqualified

            if ql2_disqualified:
                disqualification_source = "maximo"
                disqualification_reason = None
                disqualified_by_label = None
            elif manual_disqualified:
                disqualification_source = "manual"
                disqualification_reason = manual_entry.reason
                disqualified_by_label = user_names.get(manual_entry.disqualified_by, manual_entry.disqualified_by)
            else:
                disqualification_source = None
                disqualification_reason = None
                disqualified_by_label = None

            resolved[vendor] = dict(
                unit_cost=unit_cost,
                line_cost=line_cost,
                qty=qty,
                technically_disqualified=technically_disqualified,
                disqualification_source=disqualification_source,
                disqualification_reason=disqualification_reason,
                disqualified_by_label=disqualified_by_label,
                corrected=corrected,
                corrected_by_label=corrected_by_label,
                corrected_note=corrected_note,
                corrected_at=corrected_at,
            )
        resolved_by_line[linenum] = resolved

    # Pass 2: each vendor's own historical distribution of unit-cost-to-
    # peer-median ratios.
    #
    # An earlier version flagged a line whenever a vendor's unit cost was
    # >50% away from that line's peer median -- but a vendor who's simply
    # priced consistently higher (or lower) than the group across the
    # *whole* BOQ then gets "outlier" on nearly every single line, which
    # is just their overall price level, not a per-line anomaly. Real
    # construction bidders often do differ by 2-3x overall.
    #
    # Comparing each line's ratio-to-peer-median against that *same
    # vendor's own* typical ratio instead only flags a line that's
    # unusual **for them specifically** -- e.g. a vendor who's normally
    # right around the peer median but priced way off on one particular
    # line (a data-entry mistake, or the unbalanced/front-loaded pricing
    # CLAUDE.md's manual process specifically calls out). This is now a
    # real (modified) z-score against the vendor's own historical
    # median/MAD of that ratio, flagged only past OUTLIER_Z_THRESHOLD --
    # stricter than the old flat 50% check -- and at most one outlier per
    # line ever gets surfaced (see the z_candidates cap below), even if
    # more than one vendor's price happens to deviate on the same line. A
    # vendor with too few peer-comparable lines to establish a reliable
    # baseline (MIN_LINES_FOR_VENDOR_BASELINE) gets no outlier flags at
    # all rather than a noisier fallback.
    # A technically disqualified price is excluded from every one of
    # these commercial computations, same as the stakeholder ask requires
    # -- it never contributes to a peer median, a vendor's own baseline,
    # or (further below) is_lowest/contract_total.
    peer_median_by_line: dict[float, float | None] = {}
    for linenum, resolved in resolved_by_line.items():
        real_costs = [
            v["unit_cost"] for v in resolved.values()
            if v["unit_cost"] not in (None, 0) and not v["technically_disqualified"]
        ]
        peer_median_by_line[linenum] = (
            statistics.median(real_costs) if len(real_costs) >= OUTLIER_MIN_QUOTES else None
        )

    vendor_ratios: dict[str, list[float]] = {v: [] for v in submitting_vendors}
    for linenum, resolved in resolved_by_line.items():
        peer_median = peer_median_by_line[linenum]
        if not peer_median:
            continue
        for vendor, v in resolved.items():
            if v["unit_cost"] not in (None, 0) and not v["technically_disqualified"]:
                vendor_ratios[vendor].append(v["unit_cost"] / peer_median)

    # A plain mean/stdev z-score was tried first and rejected: it gets
    # "masked" by the exact outlier it's trying to catch -- one huge
    # deviation inflates its own stdev enough to shrink its own z-score
    # back under the threshold. Median/MAD (a "modified z-score",
    # Iglewicz & Hoaglin) resists that, since a single extreme point
    # barely moves either the median or the median-of-deviations.
    vendor_baseline_median: dict[str, float | None] = {}
    vendor_baseline_mad: dict[str, float | None] = {}
    for v, ratios in vendor_ratios.items():
        if len(ratios) >= MIN_LINES_FOR_VENDOR_BASELINE:
            median_ratio = statistics.median(ratios)
            mad = statistics.median([abs(r - median_ratio) for r in ratios])
            vendor_baseline_median[v] = median_ratio
            vendor_baseline_mad[v] = max(mad, MAD_FLOOR_FRACTION * abs(median_ratio))
        else:
            vendor_baseline_median[v] = None
            vendor_baseline_mad[v] = None

    # Pass 3: aggregate totals + flag every cell, now that peer medians
    # and each vendor's baseline ratio are both known.
    vendor_totals = {v: 0.0 for v in submitting_vendors}
    vendor_unquoted = {v: 0 for v in submitting_vendors}
    vendor_errors = {v: 0 for v in submitting_vendors}
    vendor_outliers = {v: 0 for v in submitting_vendors}
    vendor_zero_price = {v: 0 for v in submitting_vendors}
    vendor_disqualified = {v: 0 for v in submitting_vendors}

    all_lines: list[ComparisonLine] = []
    for linenum in sorted(resolved_by_line.keys()):
        resolved = resolved_by_line[linenum]
        canonical = canonical_by_line[linenum]
        canonical_qty = float(canonical.ORDERQTY) if canonical.ORDERQTY is not None else None
        peer_median = peer_median_by_line[linenum]

        # A technically disqualified price is real (a vendor submitted it)
        # but out of commercial play entirely -- excluded from is_lowest
        # the same way it was excluded from the peer median above.
        real_line_costs = [
            v["line_cost"] for v in resolved.values()
            if v["line_cost"] not in (None, 0) and not v["technically_disqualified"]
        ]
        min_line_cost = min(real_line_costs) if real_line_costs else None

        # At most one outlier per line: score every vendor's z-score
        # candidate first, then keep only the single largest that clears
        # the threshold -- even if more than one vendor's price happens
        # to deviate from their own norm on the same line, only the
        # strongest signal gets surfaced.
        z_candidates: list[tuple[float, str]] = []
        for vendor, v in resolved.items():
            unit_cost = v["unit_cost"]
            median_ratio = vendor_baseline_median.get(vendor)
            mad = vendor_baseline_mad.get(vendor)
            if (
                v["corrected"]
                or v["technically_disqualified"]
                or unit_cost in (None, 0)
                or not peer_median
                or median_ratio is None
                or not mad
            ):
                continue
            # 0.6745 scales MAD to be comparable to a standard deviation
            # for normally-distributed data -- the standard modified
            # z-score constant.
            z = 0.6745 * abs((unit_cost / peer_median) - median_ratio) / mad
            if z > OUTLIER_Z_THRESHOLD:
                z_candidates.append((z, vendor))
        outlier_vendor = max(z_candidates)[1] if z_candidates else None

        prices: dict[str, LinePrice] = {}
        for vendor, v in resolved.items():
            unit_cost = v["unit_cost"]
            line_cost = v["line_cost"]
            qty = v["qty"]
            corrected = v["corrected"]
            technically_disqualified = v["technically_disqualified"]

            # Original round: no independently-entered unit cost means
            # genuinely unquoted. Round-scoped view: unit_cost is derived
            # from line_cost, so line_cost is the real signal instead.
            # A disqualified vendor did submit a real price -- unquoted
            # and technically_disqualified are independent, non-
            # overlapping reasons a cell might be excluded from play.
            unquoted = (unit_cost is None) if is_original else (line_cost is None)
            zero_price = (
                not corrected and not technically_disqualified and unit_cost is not None and unit_cost == 0
            )
            is_lowest = (
                not technically_disqualified
                and line_cost is not None
                and line_cost != 0
                and min_line_cost is not None
                and line_cost == min_line_cost
            )
            arithmetic_error = (
                is_original
                and not corrected
                and not technically_disqualified
                and unit_cost is not None
                and line_cost is not None
                and qty is not None
                and abs(line_cost - qty * unit_cost) > ARITHMETIC_TOLERANCE
            )

            outlier = vendor == outlier_vendor

            if unquoted:
                vendor_unquoted[vendor] += 1
            if technically_disqualified:
                vendor_disqualified[vendor] += 1
            # A disqualified line is out of commercial evaluation
            # entirely -- per the stakeholder ask, its cost never
            # contributes to the vendor's contract total.
            if line_cost is not None and not technically_disqualified:
                vendor_totals[vendor] += line_cost
            if arithmetic_error:
                vendor_errors[vendor] += 1
            if outlier:
                vendor_outliers[vendor] += 1
            if zero_price:
                vendor_zero_price[vendor] += 1

            prices[vendor] = LinePrice(
                unit_cost=unit_cost,
                line_cost=line_cost,
                unquoted=unquoted,
                is_lowest=is_lowest,
                arithmetic_error=arithmetic_error,
                outlier=outlier,
                zero_price=zero_price,
                technically_disqualified=technically_disqualified,
                disqualification_source=v["disqualification_source"],
                disqualification_reason=v["disqualification_reason"],
                disqualified_by_label=v["disqualified_by_label"],
                corrected=corrected,
                corrected_by_label=v["corrected_by_label"],
                corrected_note=v["corrected_note"],
                corrected_at=v["corrected_at"],
            )

        all_lines.append(
            ComparisonLine(
                rfqlinenum=float(canonical.RFQLINENUM),
                description=canonical.DESCRIPTION,
                qty=canonical_qty,
                unit=canonical.ORDERUNIT,
                prices=prices,
            )
        )

    total_line_count = len(all_lines)
    truncated = total_line_count > LINES_CAP
    returned_lines = all_lines[:LINES_CAP]

    # Split-award total: if every line were awarded individually to
    # whoever's cheapest technically-accepted bidder on that specific
    # line (is_lowest, computed above), what would each vendor actually
    # get paid? Always computed over the *full* line set (all_lines),
    # never just the returned/truncated page, same invariant as every
    # other aggregate in this function. On the rare exact tie for
    # cheapest, every tied vendor is credited for that line -- there's no
    # principled way to pick a single "winner" between two identical
    # prices, so this stays honest about the tie rather than guessing.
    split_award: dict[str, dict] = {v: {"total": 0.0, "line_count": 0} for v in submitting_vendors}
    for line in all_lines:
        for vendor, price in line.prices.items():
            if price.is_lowest:
                split_award[vendor]["total"] += price.line_cost
                split_award[vendor]["line_count"] += 1

    vendors = []
    for v in sorted(submitting_vendors):
        partial_entry = partial_bids.get(v)
        is_partial_bid = partial_entry is not None and partial_entry.is_partial
        vendors.append(
            VendorSummary(
                vendor=v,
                name=vendor_names.get(v),
                contract_total=vendor_totals[v],
                # A partial bidder was never expected to price the whole
                # BOQ, so an unquoted line for them isn't a gap worth
                # flagging the way it is for a full-scope bidder -- see
                # the module docstring's partial-bids section.
                unquoted_count=0 if is_partial_bid else vendor_unquoted[v],
                arithmetic_error_count=vendor_errors[v],
                outlier_count=vendor_outliers[v],
                zero_price_count=vendor_zero_price[v],
                technically_disqualified_count=vendor_disqualified[v],
                is_partial_bid=is_partial_bid,
                quoted_line_count=total_line_count - vendor_unquoted[v],
                partial_bid_note=partial_entry.note if is_partial_bid else None,
            )
        )

    not_submitted = [
        NotSubmittedVendor(vendor=v, name=name)
        for v, name in sorted(vendor_names.items())
        if v not in submitting_vendors
    ]
    split_award_totals = [
        SplitAwardTotal(
            vendor=v,
            name=vendor_names.get(v),
            total=split_award[v]["total"],
            line_count=split_award[v]["line_count"],
        )
        for v in sorted(submitting_vendors)
    ]

    return {
        "rfqnum": rfqnum,
        "round": selected_round,
        "rounds_present": rounds_present,
        "total_line_count": total_line_count,
        "truncated": truncated,
        "vendors": [asdict(v) for v in vendors],
        "not_submitted": [asdict(v) for v in not_submitted],
        "split_award_totals": [asdict(s) for s in split_award_totals],
        "lines": [asdict(l) for l in returned_lines],
    }


@router.get("/rfqs/{rfqnum}/comparison")
async def get_comparison(rfqnum: str, round: str | None = None):
    return build_comparison(rfqnum, round_label=round)
