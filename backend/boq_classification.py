"""Classifies every RFQ by how much real line-item BOQ detail it has.

DETAILBOQAVAILABLE (a flag on `rfq`) is confirmed unreliable -- see
databricks/FINDINGS.md. The real signal is how many quotationline rows each
RFQ actually has per pricing vendor, computed here directly. This is a
single, deliberately heavy query (a GROUP BY over quotationline's 1.66M
rows), so its result is cached in-process rather than re-run per request --
see get_classifications().
"""

import threading
import time
from dataclasses import dataclass

from backend.db import CATALOG, SCHEMA, get_connection

CACHE_TTL_SECONDS = 15 * 60

LUMP_SUM = "lump_sum"
SHALLOW = "shallow"
DETAILED_BOQ = "detailed_boq"
NO_PRICING_DATA = "no_pricing_data"

CATEGORIES = (DETAILED_BOQ, SHALLOW, LUMP_SUM, NO_PRICING_DATA)


@dataclass(frozen=True)
class RfqClassification:
    rfqnum: str
    org_id: str | None
    boq_category: str
    vendor_count: int  # invited vendors, from rfqvendor -- not "priced"


def _classify(avg_lines_per_vendor: float | None) -> str:
    if avg_lines_per_vendor is None:
        return NO_PRICING_DATA
    if avg_lines_per_vendor <= 1:
        return LUMP_SUM
    if avg_lines_per_vendor <= 9:
        return SHALLOW
    return DETAILED_BOQ


_CLASSIFICATION_QUERY = f"""
    WITH boq_stats AS (
        SELECT RFQNUM, COUNT(*) / COUNT(DISTINCT VENDOR) AS avg_lines_per_vendor
        FROM {CATALOG}.{SCHEMA}.quotationline
        GROUP BY RFQNUM
    ),
    invited AS (
        SELECT RFQNUM, COUNT(DISTINCT VENDOR) AS invited_vendor_count
        FROM {CATALOG}.{SCHEMA}.rfqvendor
        GROUP BY RFQNUM
    )
    SELECT r.RFQNUM,
           r.ORGID,
           COALESCE(inv.invited_vendor_count, 0) AS vendor_count,
           bs.avg_lines_per_vendor
    FROM {CATALOG}.{SCHEMA}.rfq r
    LEFT JOIN boq_stats bs ON bs.RFQNUM = r.RFQNUM
    LEFT JOIN invited inv ON inv.RFQNUM = r.RFQNUM
"""

_lock = threading.Lock()
_cache: dict[str, RfqClassification] = {}
_cache_loaded_at: float = 0.0


def _load_classifications() -> dict[str, RfqClassification]:
    result: dict[str, RfqClassification] = {}
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(_CLASSIFICATION_QUERY)
            for row in cursor.fetchall():
                result[row.RFQNUM] = RfqClassification(
                    rfqnum=row.RFQNUM,
                    org_id=row.ORGID,
                    boq_category=_classify(row.avg_lines_per_vendor),
                    vendor_count=int(row.vendor_count),
                )
    return result


def get_classifications() -> dict[str, RfqClassification]:
    """Returns the cached RFQNUM -> RfqClassification map, refreshing it if
    the cache is empty or older than CACHE_TTL_SECONDS."""
    global _cache, _cache_loaded_at

    if _cache and (time.time() - _cache_loaded_at) < CACHE_TTL_SECONDS:
        return _cache

    with _lock:
        # Re-check after acquiring the lock -- another thread may have just
        # refreshed it while we were waiting.
        if _cache and (time.time() - _cache_loaded_at) < CACHE_TTL_SECONDS:
            return _cache
        _cache = _load_classifications()
        _cache_loaded_at = time.time()
        return _cache


def get_cache_loaded_at() -> float:
    """Unix timestamp the cache was last (re)loaded -- 0.0 if never loaded.
    Call get_classifications() first if you need this to reflect a fresh
    load rather than a stale/unset value."""
    return _cache_loaded_at
