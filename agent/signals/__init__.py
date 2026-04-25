"""
Signal acquisition modules for the Tenacious enrichment pipeline.

Each module is responsible for exactly one external signal source and returns
a SignalResult with timestamp_utc, source, confidence, and data fields.

    crunchbase  — firmographics + funding events (last 180 days)
    layoffs     — headcount reduction events (last 120 days)
    job_posts   — open-role velocity (public careers pages, robots.txt-safe)
    leadership  — CTO/VP-Eng transitions (last 90 days)

Usage:
    from agent.signals.crunchbase import get_funding_signal
    from agent.signals.layoffs import get_layoff_signal
    from agent.signals.job_posts import get_job_post_signal
    from agent.signals.leadership import get_leadership_signal
"""
from agent.signals.crunchbase import get_funding_signal
from agent.signals.layoffs import get_layoff_signal
from agent.signals.job_posts import get_job_post_signal
from agent.signals.leadership import get_leadership_signal

__all__ = [
    "get_funding_signal",
    "get_layoff_signal",
    "get_job_post_signal",
    "get_leadership_signal",
]
