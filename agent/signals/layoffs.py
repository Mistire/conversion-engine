"""
layoffs.fyi signal module — headcount reduction events.

Data source: local CSV snapshot at data/layoffs/layoffs.csv (mirrors the
public layoffs.fyi dataset). Only events within LAYOFF_WINDOW_DAYS are
considered actionable; older events are outside the ICP signal window.

ICP classification rule: a layoff event present within 120 days forces
Segment 2 (cost-restructuring) regardless of other signals, unless the
layoff percentage exceeds 40% (survival mode — abstain).

Signal window: last 120 days (configurable via LAYOFF_WINDOW_DAYS).
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent.models import Confidence, LayoffEvent, SignalResult

DATA_DIR = Path(__file__).parent.parent.parent / "data"
LAYOFFS_CSV = DATA_DIR / "layoffs" / "layoffs.csv"

LAYOFF_WINDOW_DAYS = 120
SURVIVAL_MODE_THRESHOLD_PCT = 40.0  # abstain above this percentage

_INDEX: dict[str, list[dict]] | None = None


def _load_index() -> dict[str, list[dict]]:
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    index: dict[str, list[dict]] = {}
    if not LAYOFFS_CSV.exists():
        return index
    with open(LAYOFFS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("Company") or row.get("company") or "").strip().lower()
            if name:
                index.setdefault(name, []).append(row)
    _INDEX = index
    return index


def _parse_date(event: dict) -> Optional[datetime]:
    for field in ("Date", "date", "Date Added"):
        val = event.get(field, "")
        if val:
            try:
                return datetime.strptime(val[:10], "%Y-%m-%d")
            except ValueError:
                pass
    return None


def get_layoff_signal(company_name: str) -> SignalResult:
    """
    Return a SignalResult for the most recent layoff event within LAYOFF_WINDOW_DAYS.

    Confidence rules:
      HIGH   — event within 60 days, percentage confirmed
      MEDIUM — event 61-120 days ago, or percentage missing
      LOW    — no event found, or event is outside the window

    Edge cases:
      - No CSV → LOW confidence, error field set
      - Multiple events → most recent selected
      - days_ago > LAYOFF_WINDOW_DAYS → treated as no event (not actionable)
      - Percentage > SURVIVAL_MODE_THRESHOLD_PCT → returned with data.survival_mode=True
        (caller should use this to trigger abstain path in ICP classifier)
    """
    source = str(LAYOFFS_CSV)
    now = datetime.utcnow()

    if not LAYOFFS_CSV.exists():
        return SignalResult(
            signal_type="layoffs_fyi",
            company_name=company_name,
            source=source,
            confidence=Confidence.LOW,
            data={},
            error=f"Layoffs CSV not found at {LAYOFFS_CSV}",
        )

    index = _load_index()
    key = company_name.strip().lower()
    events = index.get(key, [])
    if not events:
        for k, v in index.items():
            if key in k or k in key:
                events = v
                break

    if not events:
        return SignalResult(
            signal_type="layoffs_fyi",
            company_name=company_name,
            source=source,
            confidence=Confidence.LOW,
            data={"layoff": None},
        )

    # Most recent event only
    dated = [(e, _parse_date(e)) for e in events if _parse_date(e) is not None]
    if not dated:
        return SignalResult(
            signal_type="layoffs_fyi",
            company_name=company_name,
            source=source,
            confidence=Confidence.LOW,
            data={"layoff": None},
        )
    latest_event, latest_dt = max(dated, key=lambda x: x[1])  # type: ignore[arg-type]
    days_ago = (now - latest_dt).days  # type: ignore[operator]

    if days_ago > LAYOFF_WINDOW_DAYS:
        return SignalResult(
            signal_type="layoffs_fyi",
            company_name=company_name,
            source=source,
            confidence=Confidence.LOW,
            data={"layoff": None, "note": f"Most recent event {days_ago}d ago — outside {LAYOFF_WINDOW_DAYS}d window"},
        )

    # Parse percentage and headcount
    pct_raw = latest_event.get("Percentage") or latest_event.get("percentage") or ""
    headcount_raw = latest_event.get("Laid_Off_Count") or latest_event.get("laid_off_count") or ""

    pct: Optional[float] = None
    headcount: Optional[int] = None
    try:
        pct = float(str(pct_raw).replace("%", "").strip()) if pct_raw else None
    except ValueError:
        pass
    try:
        headcount = int(str(headcount_raw).replace(",", "").strip()) if headcount_raw else None
    except ValueError:
        pass

    layoff = LayoffEvent(
        date=latest_dt.strftime("%Y-%m-%d"),  # type: ignore[union-attr]
        headcount_cut=headcount,
        percentage_cut=pct,
        days_ago=days_ago,
    )

    # Confidence scoring
    if days_ago <= 60 and pct is not None:
        confidence = Confidence.HIGH
    elif days_ago <= LAYOFF_WINDOW_DAYS:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    survival_mode = pct is not None and pct > SURVIVAL_MODE_THRESHOLD_PCT

    return SignalResult(
        signal_type="layoffs_fyi",
        company_name=company_name,
        source=f"layoffs_csv:{company_name.lower().replace(' ', '_')}",
        confidence=confidence,
        data={
            "layoff": layoff.model_dump(),
            "survival_mode": survival_mode,
            "note": (
                f"Layoff {pct:.0f}% exceeds {SURVIVAL_MODE_THRESHOLD_PCT:.0f}% threshold — "
                "likely in survival mode, abstain recommended"
                if survival_mode else ""
            ),
        },
    )
