"""
Email handler — Resend (primary) with MailerSend fallback.
Primary outreach channel for Tenacious prospects (founders, CTOs, VPs Eng).

SAFETY: When live_mode=False (default), all outbound goes to staff_sink_email.
"""
import json
from datetime import datetime
from typing import Optional

import httpx

from agent.config import get_settings
from agent.models import HiringSignalBrief, CompetitorGapBrief, ICPSegment, Confidence, OutboundEmail

settings = get_settings()


# ─── Email composition ────────────────────────────────────────────────────────

PITCH_LANGUAGE = {
    ICPSegment.SEGMENT_1_FUNDED: {
        "high_ai": "scale your AI team faster than in-house hiring can support",
        "low_ai": "stand up your first AI function with a dedicated engineering squad",
        "hook": "you recently closed a funding round and your engineering open roles are growing",
    },
    ICPSegment.SEGMENT_2_RESTRUCTURING: {
        "high_ai": "replace higher-cost roles with offshore AI/ML capacity while maintaining delivery",
        "low_ai": "replace higher-cost roles with offshore equivalents and keep delivery on track",
        "hook": "your company has been restructuring and engineering cost discipline is top of mind",
    },
    ICPSegment.SEGMENT_3_LEADERSHIP_TRANSITION: {
        "high_ai": "reassess your offshore engineering mix with fresh eyes",
        "low_ai": "reassess your vendor contracts and offshore mix in your first 90 days",
        "hook": "you recently stepped into your role and are likely assessing your engineering vendors",
    },
    ICPSegment.SEGMENT_4_CAPABILITY_GAP: {
        "high_ai": "close the specific AI/ML capability gap between your team and sector leaders",
        "low_ai": "build the specialized ML capability your roadmap requires",
        "hook": "your AI maturity signals suggest you are investing seriously in AI systems",
    },
}


def compose_outbound_email(
    prospect_name: str,
    company_name: str,
    prospect_title: str,
    brief: HiringSignalBrief,
    gap_brief: Optional[CompetitorGapBrief] = None,
) -> OutboundEmail:
    """
    Composes a research-grounded outbound email.
    Variant = 'research_grounded' when brief has usable signals,
              'generic_pitch' as fallback when signals are weak.

    Grounded-honesty rule: agent asks rather than asserts when confidence is LOW.
    """
    segment = brief.icp_segment
    ai_score = brief.ai_maturity.score if brief.ai_maturity else 0
    ai_confidence = brief.ai_maturity.confidence if brief.ai_maturity else Confidence.LOW
    is_high_ai = ai_score >= 2 and ai_confidence != Confidence.LOW

    pitch = PITCH_LANGUAGE.get(segment, {})
    pitch_line = pitch.get("high_ai" if is_high_ai else "low_ai", "expand your engineering capacity")
    hook = pitch.get("hook", "your company fits the profile of organizations Tenacious typically partners with")

    # Build signal sentence (grounded-honesty: only assert what the data supports)
    signal_sentences: list[str] = []

    if brief.funding and brief.funding.days_ago and brief.funding.days_ago <= 180:
        amount_m = (brief.funding.amount_usd or 0) / 1_000_000
        if amount_m > 0:
            signal_sentences.append(
                f"you closed a {brief.funding.round_type} round "
                f"(~${amount_m:.0f}M) {brief.funding.days_ago} days ago"
            )
        else:
            signal_sentences.append(f"you recently closed a {brief.funding.round_type} round")

    if brief.job_posts and brief.job_posts.total_open_roles >= 5:
        signal_sentences.append(
            f"you currently have {brief.job_posts.total_open_roles} open roles"
            + (f", including {brief.job_posts.ai_adjacent_roles} AI-adjacent positions" if brief.job_posts.ai_adjacent_roles > 0 else "")
        )
    elif brief.job_posts and brief.job_posts.total_open_roles > 0:
        # Fewer than 5 roles — ask rather than assert
        signal_sentences.append(
            f"it looks like you may be in an early hiring phase ({brief.job_posts.total_open_roles} open role(s) visible publicly)"
        )

    if brief.leadership_change and brief.leadership_change.days_ago and brief.leadership_change.days_ago <= 90:
        signal_sentences.append(
            f"there was a recent {brief.leadership_change.role} transition at {company_name}"
        )

    if gap_brief and gap_brief.gaps and gap_brief.confidence != Confidence.LOW:
        top_gap = gap_brief.gaps[0]
        signal_sentences.append(f"our public data shows: {top_gap[:120]}...")

    signal_block = (
        " — specifically, " + "; and ".join(signal_sentences) + "."
        if signal_sentences
        else "."
    )

    variant = "research_grounded" if signal_sentences else "generic_pitch"

    # Low-signal fallback: softer language
    if brief.icp_confidence == Confidence.LOW or not signal_sentences:
        opening = (
            f"I came across {company_name} and wanted to reach out — "
            f"from what I can see publicly, {hook}."
        )
    else:
        opening = (
            f"I noticed {company_name}{signal_block} "
            f"That pattern typically means the next bottleneck is {pitch_line}."
        )

    subject = f"Engineering capacity for {company_name} — quick question"
    if segment == ICPSegment.SEGMENT_4_CAPABILITY_GAP and is_high_ai:
        subject = f"AI/ML capability gap at {company_name} — a research finding"

    html_body = f"""
<p>Hi {prospect_name.split()[0]},</p>

<p>{opening}</p>

<p>Tenacious Consulting and Outsourcing works with B2B technology companies at exactly this inflection point.
We provide dedicated engineering teams (Python, Go, ML/data, infra) that operate under Tenacious management
but deliver directly to your product. Typical engagement: 3–12 engineers, 6–24 months.</p>

<p>Would a 30-minute call with one of our delivery leads be useful? I can share our bench availability
and a short comparison of how similar companies at your stage typically structure this.</p>

<p>Best,<br>
Tenacious Outreach Agent<br>
<em>draft — pending Tenacious review</em></p>
""".strip()

    text_body = (
        f"Hi {prospect_name.split()[0]},\n\n"
        f"{opening}\n\n"
        "Tenacious Consulting and Outsourcing works with B2B technology companies at exactly this inflection point. "
        "We provide dedicated engineering teams (Python, Go, ML/data, infra) that operate under Tenacious management "
        "but deliver directly to your product. Typical engagement: 3–12 engineers, 6–24 months.\n\n"
        "Would a 30-minute call with one of our delivery leads be useful? "
        "I can share our bench availability and a short comparison of how similar companies at your stage typically structure this.\n\n"
        "Best,\nTenacious Outreach Agent\n[draft — pending Tenacious review]"
    )

    return OutboundEmail(
        to="",  # filled by caller
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        is_draft=True,
        variant=variant,
        prospect_name=prospect_name,
        company_name=company_name,
    )


# ─── Sending ──────────────────────────────────────────────────────────────────

async def send_email(
    to_address: str,
    email: OutboundEmail,
    trace_id: Optional[str] = None,
) -> dict:
    """
    Sends via Resend. When live_mode=False, routes to staff_sink_email.
    Returns response dict with message_id and routing info.
    """
    actual_to = settings.staff_sink_email if not settings.live_mode else to_address
    routed_to_sink = not settings.live_mode

    if not settings.resend_api_key:
        # No key — return mock response for testing
        return {
            "message_id": f"mock_{trace_id or 'test'}",
            "to": actual_to,
            "routed_to_sink": routed_to_sink,
            "status": "mock_sent",
            "timestamp": datetime.utcnow().isoformat(),
        }

    payload = {
        "from": settings.resend_from_email,
        "to": [actual_to],
        "subject": email.subject + (" [DRAFT — STAFF SINK]" if routed_to_sink else ""),
        "html": email.html_body,
        "text": email.text_body,
        "headers": {
            "X-Tenacious-Draft": "true",
            "X-Original-To": to_address,
            "X-Trace-Id": trace_id or "",
            "X-Variant": email.variant,
        },
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "message_id": data.get("id", ""),
        "to": actual_to,
        "original_to": to_address,
        "routed_to_sink": routed_to_sink,
        "status": "sent",
        "timestamp": datetime.utcnow().isoformat(),
        "variant": email.variant,
    }


async def send_reply(
    to_address: str,
    subject: str,
    text_body: str,
    html_body: str,
    thread_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> dict:
    """Send a follow-up reply in an existing thread."""
    email = OutboundEmail(
        to=to_address,
        subject=f"Re: {subject}" if not subject.startswith("Re:") else subject,
        html_body=html_body,
        text_body=text_body,
    )
    return await send_email(to_address, email, trace_id=trace_id)
