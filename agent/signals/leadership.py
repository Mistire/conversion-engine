"""
Leadership change signal module — CTO/VP-Eng transitions.

Data sources (in priority order):
  1. Frozen snapshots in data/leadership/<company>.json
  2. Crunchbase record description field (heuristic keyword match)
  3. LinkedIn "started new position" heuristic (from job-post scrape text)

Why leadership changes matter:
  New CTO/VP-Eng in the first 90 days is the highest-conversion ICP window
  (Segment 3). New leaders reassess vendor contracts and offshore mix as a
  standard practice. After 90 days the reassessment window closes.

Confidence scoring:
  HIGH   — press release or official company announcement URL found
  MEDIUM — LinkedIn "started new position" (single source, no corroboration)
  LOW    — inferred from job description keyword or Crunchbase description

Edge cases:
  - Interim/acting appointment → returned with data.is_interim=True
    (ICP classifier should abstain on interim; see B-06 in probe_library)
  - Multiple leadership changes in window → most recent returned
  - days_ago > 90 → outside ICP window, confidence capped at LOW
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent.models import Confidence, LeadershipChange, SignalResult

DATA_DIR = Path(__file__).parent.parent.parent / "data"
SNAPSHOT_DIR = DATA_DIR / "leadership"

LEADERSHIP_WINDOW_DAYS = 90
LEADERSHIP_ROLES = {"cto", "vp engineering", "vp eng", "head of engineering", "chief technology officer"}
INTERIM_KEYWORDS = {"interim", "acting", "temporary", "placeholder", "while search"}


def _snapshot_path(company_name: str) -> Path:
    return SNAPSHOT_DIR / f"{company_name.lower().replace(' ', '_')}.json"


def _detect_interim(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in INTERIM_KEYWORDS)


def _extract_from_crunchbase_desc(description: str, company_name: str, days_ago_estimate: int = 60) -> Optional[dict]:
    """
    Heuristic extraction from Crunchbase description text.
    Returns a raw dict or None.
    """
    desc_lower = description.lower()
    for role in LEADERSHIP_ROLES:
        patterns = [
            rf"new {re.escape(role)}\b",
            rf"appointed.*?{re.escape(role)}\b",
            rf"{re.escape(role)}.*?appointed\b",
            rf"hired.*?{re.escape(role)}\b",
        ]
        for pat in patterns:
            if re.search(pat, desc_lower):
                is_interim = _detect_interim(description)
                return {
                    "role": role,
                    "name": "",  # name not extractable from description heuristic
                    "days_ago": days_ago_estimate,
                    "source": "crunchbase_description_heuristic",
                    "is_interim": is_interim,
                }
    return None


def get_leadership_signal(
    company_name: str,
    crunchbase_description: Optional[str] = None,
) -> SignalResult:
    """
    Return a SignalResult for leadership changes within LEADERSHIP_WINDOW_DAYS.

    Confidence rules:
      HIGH   — press-release or official URL in snapshot
      MEDIUM — LinkedIn source in snapshot, or unambiguous Crunchbase match
      LOW    — keyword heuristic only, or outside the 90-day window

    Args:
        company_name: Company to look up.
        crunchbase_description: Raw Crunchbase description string (optional).
                                 Used as a fallback when no snapshot exists.
    """
    source_path = _snapshot_path(company_name)
    now = datetime.utcnow()

    # 1 — Frozen snapshot
    if source_path.exists():
        try:
            raw = json.loads(source_path.read_text())
            days_ago = raw.get("days_ago")
            if days_ago is not None and days_ago > LEADERSHIP_WINDOW_DAYS:
                return SignalResult(
                    signal_type="leadership_change",
                    company_name=company_name,
                    source=str(source_path),
                    confidence=Confidence.LOW,
                    data={"leadership_change": None, "note": f"Most recent change {days_ago}d ago — outside {LEADERSHIP_WINDOW_DAYS}d window"},
                )
            source_url = raw.get("source_url", "")
            is_interim = raw.get("is_interim", False)
            # Confidence based on source quality
            if "linkedin.com" in source_url:
                confidence = Confidence.MEDIUM
            elif source_url:
                confidence = Confidence.HIGH  # press release or official URL
            else:
                confidence = Confidence.LOW

            change = LeadershipChange(
                role=raw.get("role", ""),
                name=raw.get("name", ""),
                days_ago=days_ago,
                date=raw.get("date"),
            )
            return SignalResult(
                signal_type="leadership_change",
                company_name=company_name,
                source=source_url or str(source_path),
                confidence=confidence,
                data={
                    "leadership_change": change.model_dump(),
                    "is_interim": is_interim,
                    "source_url": source_url,
                },
            )
        except Exception:
            pass  # corrupt snapshot — fall through

    # 2 — Crunchbase description heuristic
    if crunchbase_description:
        extracted = _extract_from_crunchbase_desc(crunchbase_description, company_name)
        if extracted:
            change = LeadershipChange(
                role=extracted["role"],
                name=extracted.get("name", ""),
                days_ago=extracted["days_ago"],
            )
            return SignalResult(
                signal_type="leadership_change",
                company_name=company_name,
                source="crunchbase_description_heuristic",
                confidence=Confidence.LOW,
                data={
                    "leadership_change": change.model_dump(),
                    "is_interim": extracted.get("is_interim", False),
                    "note": "Heuristic extraction — verify before using in outreach",
                },
            )

    # 3 — No signal found
    return SignalResult(
        signal_type="leadership_change",
        company_name=company_name,
        source="none",
        confidence=Confidence.LOW,
        data={"leadership_change": None},
    )
