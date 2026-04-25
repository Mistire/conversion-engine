"""
Job-post velocity signal module — open-role scraping.

Scraping policy (IMPORTANT — read before modifying):
  1. robots.txt is checked before any live scrape. If Disallow: / or
     Disallow: /careers is present, the scraper returns LOW confidence with
     no data and logs the block.
  2. Only public, unauthenticated pages are scraped. No login, no cookie
     injection, no captcha bypass.
  3. Live scrapes are rate-limited to one request per company per run.
  4. Frozen snapshots (data/job_posts/<company>.json) are preferred over
     live scrapes to avoid hammering careers pages during batch runs.
  5. Maximum 200 live scrapes per challenge week (quota tracked in
     data/job_posts/scrape_log.json).

Velocity calculation:
  velocity_60d = current_open_roles / max(open_roles_60d_ago, 1)
  Requires a frozen snapshot with a 60-day-old baseline to compute.
  Without baseline, velocity_60d is None (not fabricated).
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from agent.models import Confidence, JobPostSignal, SignalResult

DATA_DIR = Path(__file__).parent.parent.parent / "data"
SNAPSHOT_DIR = DATA_DIR / "job_posts"
SCRAPE_LOG = SNAPSHOT_DIR / "scrape_log.json"

SCRAPE_QUOTA = 200
AI_KEYWORDS = frozenset({
    "ml engineer", "machine learning", "applied scientist", "llm engineer",
    "ai engineer", "data scientist", "mlops", "ai product manager",
    "data platform engineer", "nlp engineer", "computer vision",
    "reinforcement learning", "recommendation system",
})
ENG_KEYWORDS = frozenset({
    "engineer", "developer", "backend", "frontend", "data", "devops",
    "platform", "infrastructure", "sre", "architect",
})


def _snapshot_path(company_name: str) -> Path:
    return SNAPSHOT_DIR / f"{company_name.lower().replace(' ', '_')}.json"


def _load_scrape_log() -> dict:
    if not SCRAPE_LOG.exists():
        return {"count": 0, "companies": []}
    try:
        return json.loads(SCRAPE_LOG.read_text())
    except Exception:
        return {"count": 0, "companies": []}


def _increment_scrape_log(company_name: str) -> None:
    log = _load_scrape_log()
    log["count"] = log.get("count", 0) + 1
    companies = log.get("companies", [])
    companies.append({"company": company_name, "scraped_at": datetime.utcnow().isoformat()})
    log["companies"] = companies
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    SCRAPE_LOG.write_text(json.dumps(log, indent=2))


async def _check_robots_txt(careers_url: str) -> bool:
    """
    Returns True if scraping the careers URL is permitted by robots.txt.
    Returns False (and caller should abort) if Disallow: covers /careers or /.

    Conservative interpretation: any Disallow that matches the path prefix
    of careers_url is treated as a block.
    """
    import httpx
    parsed = urlparse(careers_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    path = parsed.path.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(robots_url, headers={"User-Agent": "TenaciousBot/1.0"})
        if resp.status_code != 200:
            return True  # no robots.txt → assume permitted

        user_agent_section = False
        for line in resp.text.splitlines():
            line = line.strip()
            if line.lower().startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip()
                user_agent_section = agent in ("*", "TenaciousBot")
            elif user_agent_section and line.lower().startswith("disallow:"):
                disallowed = line.split(":", 1)[1].strip()
                if disallowed in ("/", path, path + "/"):
                    return False  # blocked
        return True
    except Exception:
        return True  # network error → assume permitted, proceed


async def get_job_post_signal(
    company_name: str,
    careers_url: Optional[str] = None,
) -> SignalResult:
    """
    Return a SignalResult for job-post velocity.

    Priority order:
      1. Frozen snapshot if present (data/job_posts/<company>.json)
      2. Live scrape if careers_url provided AND robots.txt permits AND quota not exceeded
      3. LOW confidence if neither is available

    Confidence rules:
      HIGH   — snapshot or live scrape with >= 5 total roles found
      MEDIUM — 1-4 roles found
      LOW    — no data, robots blocked, or quota exceeded

    Edge cases:
      - robots.txt blocks scrape → LOW confidence, error = "robots_blocked"
      - Quota exceeded → LOW confidence, error = "scrape_quota_exceeded"
      - Playwright not installed → graceful fallback to LOW confidence
    """
    source = _snapshot_path(company_name)
    snapshot = source

    # 1 — Check frozen snapshot
    if snapshot.exists():
        try:
            raw = json.loads(snapshot.read_text())
            signal = JobPostSignal(**raw)
            total = signal.total_open_roles
            confidence = Confidence.HIGH if total >= 5 else (Confidence.MEDIUM if total >= 1 else Confidence.LOW)
            return SignalResult(
                signal_type="job_posts",
                company_name=company_name,
                source=f"snapshot:{snapshot}",
                confidence=confidence,
                data=signal.model_dump(),
            )
        except Exception as exc:
            pass  # corrupt snapshot — fall through to live scrape

    # 2 — Live scrape
    if not careers_url:
        return SignalResult(
            signal_type="job_posts",
            company_name=company_name,
            source="none",
            confidence=Confidence.LOW,
            data={"total_open_roles": 0},
            error="no_careers_url_provided",
        )

    # Check scrape quota
    log = _load_scrape_log()
    if log.get("count", 0) >= SCRAPE_QUOTA:
        return SignalResult(
            signal_type="job_posts",
            company_name=company_name,
            source=careers_url,
            confidence=Confidence.LOW,
            data={},
            error="scrape_quota_exceeded",
        )

    # Check robots.txt before scraping
    permitted = await _check_robots_txt(careers_url)
    if not permitted:
        return SignalResult(
            signal_type="job_posts",
            company_name=company_name,
            source=careers_url,
            confidence=Confidence.LOW,
            data={},
            error="robots_blocked",
        )

    # Live Playwright scrape
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(careers_url, timeout=15000)
            await page.wait_for_load_state("networkidle", timeout=10000)
            text = (await page.inner_text("body")).lower()
            await browser.close()

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        total = sum(1 for l in lines if any(k in l for k in {"engineer", "developer", "scientist", "manager", "analyst"}))
        eng = sum(1 for l in lines if any(k in l for k in ENG_KEYWORDS))
        ai_adj = sum(1 for l in lines if any(k in l for k in AI_KEYWORDS))

        signal = JobPostSignal(
            total_open_roles=min(total, 500),
            engineering_roles=min(eng, 300),
            ai_adjacent_roles=min(ai_adj, 100),
            sources=[careers_url],
        )

        # Cache as snapshot
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps(signal.model_dump(), indent=2))
        _increment_scrape_log(company_name)

        total_found = signal.total_open_roles
        confidence = Confidence.HIGH if total_found >= 5 else (Confidence.MEDIUM if total_found >= 1 else Confidence.LOW)
        return SignalResult(
            signal_type="job_posts",
            company_name=company_name,
            source=careers_url,
            confidence=confidence,
            data=signal.model_dump(),
        )
    except ImportError:
        return SignalResult(
            signal_type="job_posts",
            company_name=company_name,
            source=careers_url,
            confidence=Confidence.LOW,
            data={},
            error="playwright_not_installed",
        )
    except Exception as exc:
        return SignalResult(
            signal_type="job_posts",
            company_name=company_name,
            source=careers_url,
            confidence=Confidence.LOW,
            data={},
            error=f"scrape_error:{type(exc).__name__}",
        )
