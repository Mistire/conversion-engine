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
    honesty_constraints: str = "",
) -> OutboundEmail:
    """
    Composes a research-grounded outbound email.
    Variant = 'research_grounded' when brief has usable signals,
              'generic_pitch' as fallback when signals are weak or
              honesty_gate fires the abstention path.

    honesty_constraints: output of honesty_gate.build_constraints().
    When it contains 'ABSTAIN', the function returns a generic email
    without any segment-specific language or signal claims.
    """
    # ── Abstention path (F1-G, B-09) ─────────────────────────────────
    # Gate fires when icp_confidence=LOW or icp_segment=NO_MATCH.
    # Return a bare generic email — no signal claims, no segment framing.
    use_abstain = (
        "ABSTAIN" in honesty_constraints
        or brief.icp_confidence == Confidence.LOW
        or brief.icp_segment == ICPSegment.NO_MATCH
    )
    if use_abstain:
        first_name = prospect_name.split()[0]
        html_body = (
            f"<p>Hi {first_name},</p>"
            f"<p>I came across {company_name} and wanted to reach out. "
            "We work with B2B technology companies on engineering team scaling and "
            "specialized capability builds — happy to share more if the timing is right.</p>"
            "<p>Worth a 15-minute conversation? → [Cal.com link]</p>"
            "<p>Best,<br>Tenacious Outreach Agent<br>"
            "<em>draft — pending Tenacious review</em></p>"
        )
        text_body = (
            f"Hi {first_name},\n\n"
            f"I came across {company_name} and wanted to reach out. "
            "We work with B2B technology companies on engineering team scaling and "
            "specialized capability builds — happy to share more if the timing is right.\n\n"
            "Worth a 15-minute conversation? → [Cal.com link]\n\n"
            "Best,\nTenacious Outreach Agent\n[draft — pending Tenacious review]"
        )
        return OutboundEmail(
            to="",
            subject=f"Context: engineering capacity for {company_name}",
            html_body=html_body,
            text_body=text_body,
            is_draft=True,
            variant="generic_pitch",
            prospect_name=prospect_name,
            company_name=company_name,
        )

    segment = brief.icp_segment
    ai_score = brief.ai_maturity.score if brief.ai_maturity else 0
    ai_confidence = brief.ai_maturity.confidence if brief.ai_maturity else Confidence.LOW
    # F1-B: only assert high AI when score >= 2 AND confidence is not LOW
    is_high_ai = ai_score >= 2 and ai_confidence == Confidence.HIGH

    pitch = PITCH_LANGUAGE.get(segment, {})
    pitch_line = pitch.get("high_ai" if is_high_ai else "low_ai", "expand your engineering capacity")
    hook = pitch.get("hook", "your company fits the profile of organizations Tenacious typically partners with")

    # ── F1-C: suppress growth language when layoff detected ───────────
    layoff_active = (
        brief.layoff is not None
        and brief.layoff.days_ago is not None
        and brief.layoff.days_ago <= 120
        and "LAYOFF SIGNAL" in honesty_constraints
    )

    # Build signal sentences (grounded-honesty: only assert what data supports)
    signal_sentences: list[str] = []

    if brief.funding and brief.funding.days_ago and brief.funding.days_ago <= 180 and not layoff_active:
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
        # F1-A: fewer than 5 roles — ask rather than assert velocity
        signal_sentences.append(
            f"it looks like you may be in an early hiring phase "
            f"({brief.job_posts.total_open_roles} open role(s) visible publicly)"
        )

    if brief.leadership_change and brief.leadership_change.days_ago and brief.leadership_change.days_ago <= 90:
        signal_sentences.append(
            f"there was a recent {brief.leadership_change.role} transition at {company_name}"
        )

    # F1-D/F1-F: only include gap brief claims when confidence >= MEDIUM and not stale
    if gap_brief and gap_brief.gaps and gap_brief.confidence == Confidence.HIGH:
        top_gap = gap_brief.gaps[0]
        signal_sentences.append(f"our public data shows: {top_gap[:120]}...")
    elif gap_brief and gap_brief.gaps and gap_brief.confidence == Confidence.MEDIUM and "STALE" not in honesty_constraints:
        top_gap = gap_brief.gaps[0]
        signal_sentences.append(f"we've seen some signal in your sector: {top_gap[:100]}…")

    signal_block = (
        " — specifically, " + "; and ".join(signal_sentences) + "."
        if signal_sentences
        else "."
    )

    variant = "research_grounded" if signal_sentences else "generic_pitch"

    # Low-signal fallback: softer language
    if not signal_sentences:
        opening = (
            f"I came across {company_name} and wanted to reach out — "
            f"from what I can see publicly, {hook}."
        )
    elif layoff_active:
        # F1-C: post-layoff framing — cost/delivery, not growth
        opening = (
            f"I noticed {company_name} has been restructuring. "
            "That typically raises the question of how to maintain engineering "
            f"delivery velocity while reshaping cost structure — {pitch_line}."
        )
    else:
        opening = (
            f"I noticed {company_name}{signal_block} "
            f"That pattern typically means the next bottleneck is {pitch_line}."
        )

    # Subject line: Direct tone marker — no "quick question", lead with intent signal
    if segment == ICPSegment.SEGMENT_3_LEADERSHIP_TRANSITION:
        first_name = prospect_name.split()[0]
        subject = f"Context: {first_name}'s first 90 days at {company_name}"
    elif segment == ICPSegment.SEGMENT_4_CAPABILITY_GAP and is_high_ai:
        subject = f"Question: AI/ML capability gap at {company_name}"
    elif segment == ICPSegment.SEGMENT_2_RESTRUCTURING:
        subject = f"Note on {company_name} engineering capacity"
    else:
        subject = f"Context: engineering capacity for {company_name}"

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

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        status = "sent"
        message_id = data.get("id", "")
    except httpx.HTTPStatusError as exc:
        # Log the API error but do not crash — sink routing still recorded.
        status = f"api_error_{exc.response.status_code}"
        message_id = f"error_{exc.response.status_code}"
    except Exception as exc:
        status = f"send_error"
        message_id = "error_unknown"

    return {
        "message_id": message_id,
        "to": actual_to,
        "original_to": to_address,
        "routed_to_sink": routed_to_sink,
        "status": status,
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
