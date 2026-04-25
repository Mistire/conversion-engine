"""
Honesty gate — Act IV mechanism.

Reads structured confidence signals from the HiringSignalBrief and
CompetitorGapBrief and returns a phrasing-constraint block to prepend
to the LLM system prompt before any outreach composition call.

Design principle: the gate is purely deterministic (no LLM call). It
reads four fields that the enrichment pipeline already populates and
emits specific natural-language constraints the downstream LLM must
follow. This means the gate adds < 1ms latency and is fully testable
without API credits.

Fixes targeted: F1 sub-types A-F from failure_taxonomy.md:
  F1-A  weak hiring velocity → ask-mode
  F1-B  low AI maturity confidence → ask-mode
  F1-C  layoff present → no growth language
  F1-D  low-confidence gap brief → question framing
  F1-E  inferred stack → hedged attribution
  F1-F  stale brief (> 7 days) → suppress competitor claims
  F1-G  segment_confidence LOW → abstain from segment-specific pitch
"""
from datetime import datetime, timezone
from typing import Optional

from agent.models import (
    HiringSignalBrief, CompetitorGapBrief,
    ICPSegment, Confidence,
)

# Threshold mirrors the schema: segment_confidence < 0.6 → abstain.
# The model uses Confidence enum (HIGH/MEDIUM/LOW) rather than a float,
# so LOW maps to the abstain path.
_ABSTAIN_CONFIDENCES = {Confidence.LOW}

# Jobs threshold from style guide: < 5 open roles → ask, don't assert.
_WEAK_VELOCITY_THRESHOLD = 5

# Brief staleness window from the schema description.
_BRIEF_STALE_DAYS = 7


def should_abstain(brief: HiringSignalBrief) -> bool:
    """
    Returns True when the brief confidence is too low to send a
    segment-specific pitch. The agent must send a generic exploratory
    email instead.

    Maps to probe B-09 and F1-G.
    """
    return (
        brief.icp_confidence in _ABSTAIN_CONFIDENCES
        or brief.icp_segment == ICPSegment.NO_MATCH
    )


def _gap_brief_is_stale(gap_brief: CompetitorGapBrief) -> bool:
    try:
        generated = datetime.fromisoformat(gap_brief.generated_at)
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - generated).days
        return age_days > _BRIEF_STALE_DAYS
    except Exception:
        return True  # treat unparseable timestamps as stale


def build_constraints(
    brief: HiringSignalBrief,
    gap_brief: Optional[CompetitorGapBrief] = None,
) -> str:
    """
    Returns a multi-line constraint block (may be empty string) to
    prepend to the LLM system prompt under a named header.

    Called in agent.py before every LLM composition call. The block is
    empty when all signals are high-confidence, so there is no prompt
    bloat on clean briefs.
    """
    constraints: list[str] = []

    # ── F1-G: abstention ──────────────────────────────────────────────
    if should_abstain(brief):
        constraints.append(
            "ABSTAIN: confidence in ICP segment match is too low for a "
            "segment-specific pitch. Write a SHORT generic exploratory email "
            "only. Do NOT reference any segment, funding event, layoff, or "
            "capability gap. One ask, max 80 words, no segment framing."
        )
        # Abstention supersedes all other constraints — return early.
        return _wrap(constraints)

    # ── F1-A: weak hiring velocity ────────────────────────────────────
    open_roles = (brief.job_posts.total_open_roles if brief.job_posts else 0)
    if open_roles < _WEAK_VELOCITY_THRESHOLD:
        constraints.append(
            "HIRING VELOCITY: fewer than 5 open roles are publicly visible. "
            "Do NOT write 'scaling aggressively', 'hiring fast', or 'rapid growth'. "
            "Instead ASK: e.g. 'you have N open role(s) visible — is hiring "
            "velocity matching the runway?'"
        )

    # ── F1-B: low AI maturity confidence ─────────────────────────────
    if brief.ai_maturity:
        if brief.ai_maturity.confidence == Confidence.LOW:
            constraints.append(
                "AI MATURITY: confidence in the AI maturity score is LOW. "
                "Do NOT assert 'you have a strong AI team' or 'you are investing "
                "in AI'. Use hedged language: 'from what I can see publicly, it "
                "looks like you may be building an AI function — is that accurate?' "
                "or omit AI language entirely."
            )
        elif brief.ai_maturity.score >= 2 and brief.ai_maturity.confidence == Confidence.MEDIUM:
            constraints.append(
                "AI MATURITY: score is 2+ but confidence is only MEDIUM. "
                "Frame AI references as observations, not assertions: "
                "'your job posts suggest an AI-adjacent focus — curious how "
                "that function is structured.'"
            )

    # ── F1-C: layoff present → no growth language ─────────────────────
    if brief.layoff and brief.layoff.days_ago is not None and brief.layoff.days_ago <= 120:
        pct = brief.layoff.percentage_cut
        constraints.append(
            "LAYOFF SIGNAL: a layoff event was detected "
            + (f"({pct:.0f}% headcount reduction) " if pct else "")
            + "in the last 120 days. "
            "Do NOT use 'scale', 'grow', 'expand', 'hiring momentum', or any "
            "growth-oriented language. Use cost-discipline framing only: "
            "'preserve delivery capacity', 'maintain velocity through the restructure'."
        )

    # ── F1-E: inferred stack not confirmed ───────────────────────────
    if brief.tech_stack:
        constraints.append(
            "TECH STACK: the tech stack was inferred from job posts and is not "
            "confirmed. Do NOT write 'your Python/FastAPI stack' as fact. Write: "
            "'we noticed X in your job posts — if that is your primary stack…'"
        )

    # ── F1-D / F1-F: competitor gap brief ────────────────────────────
    if gap_brief is not None:
        if _gap_brief_is_stale(gap_brief):
            constraints.append(
                "STALE GAP BRIEF: the competitor gap brief is more than 7 days "
                "old. Do NOT reference specific competitor names or gap findings. "
                "Use only generic sector framing if needed."
            )
        elif gap_brief.confidence == Confidence.LOW:
            constraints.append(
                "LOW-CONFIDENCE GAP: no gap finding has high confidence. "
                "Do NOT assert competitor practices as facts. "
                "Frame as a question: 'we have seen some signal of this pattern "
                "in your sector — curious whether it applies to you.'"
            )

    return _wrap(constraints)


def _wrap(constraints: list[str]) -> str:
    if not constraints:
        return ""
    lines = ["### HONESTY CONSTRAINTS FOR THIS DRAFT", ""]
    for i, c in enumerate(constraints, 1):
        lines.append(f"{i}. {c}")
    lines.append("")
    lines.append(
        "These constraints are non-negotiable. Violating any of them is a "
        "Tenacious brand policy violation. When in doubt, ask rather than assert."
    )
    lines.append("")
    return "\n".join(lines)
