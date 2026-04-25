"""
Crunchbase signal module — firmographics + funding events.

Data source: local CSV snapshot at data/crunchbase/crunchbase_sample.csv.
In production this would be replaced by the Crunchbase Basic API or
a licensed data feed; the CSV approach is used during the challenge week
to avoid API rate limits and credential requirements.

Every result is wrapped in a SignalResult so the caller has a consistent
interface regardless of whether data was found, missing, or erroneous.

Signal window: last 180 days (configurable via FUNDING_WINDOW_DAYS).
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent.models import Confidence, FundingEvent, SignalResult

DATA_DIR = Path(__file__).parent.parent.parent / "data"
CRUNCHBASE_CSV = DATA_DIR / "crunchbase" / "crunchbase_sample.csv"

FUNDING_WINDOW_DAYS = 180

_INDEX: dict[str, dict] | None = None


def _load_index() -> dict[str, dict]:
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    index: dict[str, dict] = {}
    if not CRUNCHBASE_CSV.exists():
        return index
    with open(CRUNCHBASE_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or row.get("organization_name") or "").strip().lower()
            if name:
                index[name] = row
    _INDEX = index
    return index


def _lookup(company_name: str) -> Optional[dict]:
    index = _load_index()
    key = company_name.strip().lower()
    if key in index:
        return index[key]
    for k, v in index.items():
        if key in k or k in key:
            return v
    return None


def get_funding_signal(company_name: str) -> SignalResult:
    """
    Return a SignalResult with funding data for company_name.

    Confidence rules:
      HIGH   — round_type is Series A or B, amount confirmed, days_ago ≤ 90
      MEDIUM — round_type present but amount missing, or days_ago 91-180
      LOW    — no record found or no funding fields populated

    Edge cases:
      - CSV missing → LOW confidence, error field set
      - Partial record (date but no amount) → MEDIUM
      - days_ago > FUNDING_WINDOW_DAYS → no funding event returned (out of window)
    """
    now = datetime.utcnow()
    source = str(CRUNCHBASE_CSV)

    if not CRUNCHBASE_CSV.exists():
        return SignalResult(
            signal_type="crunchbase_funding",
            company_name=company_name,
            source=source,
            confidence=Confidence.LOW,
            data={},
            error=f"Crunchbase CSV not found at {CRUNCHBASE_CSV}",
        )

    record = _lookup(company_name)
    if not record:
        return SignalResult(
            signal_type="crunchbase_funding",
            company_name=company_name,
            source=source,
            confidence=Confidence.LOW,
            data={"employee_count": None, "sector": "", "location": ""},
        )

    # Firmographics (always populated if record exists)
    sector = (record.get("category_list") or record.get("category_groups_list") or "").split(",")[0].strip()
    location_city = record.get("city") or ""
    location_country = record.get("country_code") or record.get("country") or ""
    location = f"{location_city}, {location_country}".strip(", ")
    crunchbase_id = record.get("uuid") or record.get("id") or record.get("permalink") or ""
    try:
        employee_count = int(record.get("employee_count") or record.get("num_employees_enum") or 0)
    except (ValueError, TypeError):
        employee_count = None

    # Funding event
    funding_total_raw = record.get("total_funding_usd") or record.get("funding_total_usd") or ""
    last_funding_date_raw = record.get("last_funding_at") or ""
    round_type = record.get("last_funding_round_type") or record.get("last_funding_type") or ""

    funding: Optional[FundingEvent] = None
    days_ago: Optional[int] = None
    if last_funding_date_raw:
        try:
            dt = datetime.strptime(last_funding_date_raw[:10], "%Y-%m-%d")
            days_ago = (now - dt).days
        except ValueError:
            pass

    amount: Optional[float] = None
    try:
        amount = float(str(funding_total_raw).replace(",", "").replace("$", "")) if funding_total_raw else None
    except (ValueError, TypeError):
        pass

    if days_ago is not None and days_ago <= FUNDING_WINDOW_DAYS:
        funding = FundingEvent(
            round_type=round_type,
            amount_usd=amount,
            date=last_funding_date_raw[:10],
            days_ago=days_ago,
        )

    # Confidence scoring
    if funding:
        is_series_ab = round_type.lower() in ("series_a", "series_b", "series a", "series b", "a", "b")
        if is_series_ab and amount and days_ago is not None and days_ago <= 90:
            confidence = Confidence.HIGH
        elif round_type and days_ago is not None and days_ago <= FUNDING_WINDOW_DAYS:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW
    else:
        confidence = Confidence.LOW

    return SignalResult(
        signal_type="crunchbase_funding",
        company_name=company_name,
        source=f"crunchbase_csv:{crunchbase_id or company_name}",
        confidence=confidence,
        data={
            "crunchbase_id": crunchbase_id,
            "sector": sector,
            "employee_count": employee_count,
            "location": location,
            "funding": funding.model_dump() if funding else None,
        },
    )
