"""
Main LLM agent orchestrator.

Handles:
- Composing and sending research-grounded cold outreach (email)
- Qualifying prospects via hiring signal brief + ICP classifier
- Multi-turn email/SMS conversation management
- Booking discovery calls via Cal.com
- Writing all events to HubSpot CRM
- Grounded-honesty enforcement (no over-claiming)
- Bench-gated commitment policy (no capacity promises without bench data)
- Channel routing: email → SMS → voice
"""
import json
import uuid
import asyncio
from datetime import datetime
from typing import Optional

import httpx
from openai import AsyncOpenAI  # used via OpenRouter

from agent.config import get_settings
from agent.models import (
    ICPSegment, Confidence, ProspectContact, ConversationTurn,
    HiringSignalBrief, CompetitorGapBrief,
)
from agent.enrichment import enrich_prospect
from agent.email_handler import compose_outbound_email, send_email, send_reply
from agent.sms_handler import (
    send_sms, is_stop_command, is_booking_intent,
    compose_scheduling_sms, compose_warm_followup_sms, handle_stop_command,
)
from agent.hubspot_client import (
    upsert_contact, log_email_activity, log_sms_activity, mark_discovery_call_booked,
)
from agent.calcom_client import get_available_slots, create_booking, format_slots_list
from agent.honesty_gate import build_constraints, should_abstain

settings = get_settings()


def _llm_client() -> AsyncOpenAI:
    """Returns OpenAI-compatible client pointed at OpenRouter."""
    return AsyncOpenAI(
        api_key=settings.openrouter_api_key or "sk-placeholder",
        base_url="https://openrouter.ai/api/v1",
    )


SYSTEM_PROMPT = """You are the Tenacious Outreach Agent — an automated SDR assistant for Tenacious Consulting and Outsourcing.

Your role:
- Engage with B2B prospects (founders, CTOs, VPs Engineering) via email and SMS
- Qualify prospects against the Tenacious ICP (4 segments)
- Ground every claim in the prospect's hiring signal brief
- Book discovery calls with Tenacious delivery leads via Cal.com
- Write every interaction to HubSpot CRM

GROUNDED-HONESTY RULES (non-negotiable):
1. Never assert a claim you cannot ground in the hiring signal brief
2. If job-post signal shows fewer than 5 open roles, ASK rather than assert "aggressive hiring"
3. Never commit to bench capacity — if prospect asks for specific staffing, say a delivery lead will confirm
4. If AI maturity confidence is LOW, use softer language ("it looks like...", "from what I can see publicly...")
5. Never fabricate case study names, client logos, or ACV numbers beyond the provided pricing sheet

SEGMENT-SPECIFIC PITCH RULES:
- Segment 4 (capability gap): only pitch if AI maturity >= 2
- Segment 1 (funded): at high AI readiness, emphasise AI team scaling; at low, emphasise first AI function
- Segment 2 (restructuring): emphasise cost discipline and delivery maintenance
- Segment 3 (leadership transition): emphasise vendor reassessment window

CHANNEL RULES:
- Email is PRIMARY (cold outreach, follow-ups, research findings)
- SMS is SECONDARY (warm leads only, for scheduling coordination after email reply)
- Voice is for booked discovery calls — do not initiate cold voice outreach

TONE (Tenacious style guide):
- Direct, specific, respectful of the prospect's time
- Research-forward, not salesy
- No buzzwords. No superlatives. No "synergy" or "best-in-class"
- Reference verifiable public facts; hedge appropriately when uncertain
"""


async def _llm_reply(
    messages: list[dict],
    trace_id: str,
) -> str:
    """Call OpenRouter dev-tier LLM and return text response."""
    if not settings.openrouter_api_key:
        return "[LLM not configured — add OPENROUTER_API_KEY to .env]"

    client = _llm_client()
    response = await client.chat.completions.create(
        model=settings.openrouter_model,
        messages=messages,
        temperature=0.3,
        max_tokens=800,
    )
    return response.choices[0].message.content or ""


async def _langfuse_trace(
    trace_id: str,
    name: str,
    input_data: dict,
    output_data: dict,
    cost_usd: float = 0.0,
) -> None:
    """Write a trace to Langfuse (fire-and-forget)."""
    if not settings.langfuse_public_key:
        return
    try:
        from langfuse import Langfuse
        lf = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        trace = lf.trace(id=trace_id, name=name)
        trace.generation(
            name=name,
            input=input_data,
            output=output_data,
            usage={"total_cost": cost_usd},
        )
        lf.flush()
    except Exception:
        pass  # observability should not block the agent


# ─── Core agent actions ───────────────────────────────────────────────────────

async def initiate_outreach(prospect: ProspectContact) -> dict:
    """
    Full pipeline for a new prospect:
    1. Enrich via signal pipeline
    2. Classify ICP segment
    3. Compose research-grounded email
    4. Send email (or route to sink if live_mode=False)
    5. Upsert HubSpot contact with all enrichment fields
    6. Log email activity in HubSpot
    """
    trace_id = str(uuid.uuid4())
    t_start = datetime.utcnow()

    # Step 1-2: Enrich
    brief, gap_brief = await enrich_prospect(
        company_name=prospect.company_name,
        contact_email=prospect.email,
        careers_url=f"https://{prospect.company_domain}/careers" if prospect.company_domain else None,
    )
    prospect.hiring_signal_brief = brief
    prospect.competitor_gap_brief = gap_brief

    # Step 3: Compose email — gate fires before composition
    honesty_constraints = build_constraints(brief, gap_brief)
    email = compose_outbound_email(
        prospect_name=prospect.name,
        company_name=prospect.company_name,
        prospect_title=prospect.title,
        brief=brief,
        gap_brief=gap_brief,
        honesty_constraints=honesty_constraints,
    )
    email.to = prospect.email

    # Step 4: Send
    t_send = datetime.utcnow()
    send_result = await send_email(prospect.email, email, trace_id=trace_id)
    latency_ms = int((datetime.utcnow() - t_start).total_seconds() * 1000)

    # Step 5: HubSpot upsert
    contact_id = await upsert_contact(prospect)
    prospect.hubspot_contact_id = contact_id
    prospect.email_thread_active = True

    # Step 6: Log email activity
    if contact_id:
        await log_email_activity(
            contact_id=contact_id,
            subject=email.subject,
            body=email.html_body,
            direction="OUTBOUND",
            trace_id=trace_id,
        )

    # Langfuse trace
    await _langfuse_trace(
        trace_id=trace_id,
        name="initiate_outreach",
        input_data={
            "company": prospect.company_name,
            "segment": brief.icp_segment.value,
            "ai_maturity": brief.ai_maturity.score if brief.ai_maturity else 0,
            "variant": email.variant,
        },
        output_data={
            "send_result": send_result,
            "latency_ms": latency_ms,
        },
    )

    return {
        "trace_id": trace_id,
        "status": "sent",
        "variant": email.variant,
        "icp_segment": brief.icp_segment.value,
        "icp_confidence": brief.icp_confidence.value,
        "ai_maturity": brief.ai_maturity.score if brief.ai_maturity else 0,
        "send_result": send_result,
        "hubspot_contact_id": contact_id,
        "latency_ms": latency_ms,
        "hiring_signal_brief": brief.model_dump(),
        "competitor_gap_brief": gap_brief.model_dump(),
    }


async def handle_email_reply(
    prospect: ProspectContact,
    reply_text: str,
    subject: str,
) -> dict:
    """
    Handle an inbound email reply from a prospect.
    - If booking intent detected: send available Cal.com slots
    - Otherwise: use LLM to compose a contextual reply
    - Always log to HubSpot
    - If warm and scheduling preferred: offer to switch to SMS
    """
    trace_id = str(uuid.uuid4())
    t_start = datetime.utcnow()

    brief = prospect.hiring_signal_brief
    segment = brief.icp_segment.value if brief else "unknown"

    # Gate: build constraints from brief before LLM call
    honesty_constraints = build_constraints(brief, prospect.competitor_gap_brief) if brief else ""
    gated_system_prompt = (honesty_constraints + "\n" + SYSTEM_PROMPT) if honesty_constraints else SYSTEM_PROMPT

    conversation = [
        {"role": "system", "content": gated_system_prompt},
        {
            "role": "user",
            "content": (
                f"Prospect: {prospect.name} ({prospect.title} at {prospect.company_name})\n"
                f"ICP Segment: {segment}\n"
                f"AI Maturity: {brief.ai_maturity.score if brief and brief.ai_maturity else 'unknown'}/3\n\n"
                f"Their reply:\n{reply_text}\n\n"
                "Compose a brief, grounded reply (max 150 words). "
                "If they are interested in a call, offer 3 time slots from Cal.com. "
                "Do not over-claim. Do not promise specific bench capacity."
            ),
        },
    ]

    # Check for booking intent before LLM call (saves cost)
    if is_booking_intent(reply_text):
        slots = await get_available_slots(days_ahead=5)
        slot_list = format_slots_list(slots)
        reply_body = (
            f"Great to hear from you, {prospect.name.split()[0]}! Here are a few times that work:\n\n"
            f"{slot_list}\n\n"
            "Just reply with your preferred slot and I'll send a calendar invite. "
            "Alternatively, book directly: [Cal.com link]"
        )
        variant = "booking_offer"
    else:
        reply_body = await _llm_reply(conversation, trace_id)
        variant = "llm_reply"

    # Send reply
    reply_result = await send_reply(
        to_address=prospect.email,
        subject=subject,
        text_body=reply_body,
        html_body=f"<p>{reply_body.replace(chr(10), '</p><p>')}</p>",
        trace_id=trace_id,
    )

    latency_ms = int((datetime.utcnow() - t_start).total_seconds() * 1000)

    # Log to HubSpot
    if prospect.hubspot_contact_id:
        await log_email_activity(
            contact_id=prospect.hubspot_contact_id,
            subject=f"INBOUND: {subject}",
            body=reply_text,
            direction="INBOUND",
            trace_id=trace_id,
        )
        await log_email_activity(
            contact_id=prospect.hubspot_contact_id,
            subject=f"OUTBOUND: Re: {subject}",
            body=reply_body,
            direction="OUTBOUND",
            trace_id=trace_id,
        )

    return {
        "trace_id": trace_id,
        "variant": variant,
        "reply_sent": True,
        "reply_result": reply_result,
        "latency_ms": latency_ms,
    }


async def handle_sms_inbound(
    prospect: ProspectContact,
    message_text: str,
) -> dict:
    """
    Handle inbound SMS from a warm lead.
    - STOP commands: immediately deactivate
    - Booking intent: send Cal.com link
    - Other: brief LLM reply
    """
    trace_id = str(uuid.uuid4())

    if is_stop_command(message_text):
        result = handle_stop_command(prospect.phone or "")
        prospect.sms_thread_active = False
        if prospect.hubspot_contact_id:
            await log_sms_activity(
                prospect.hubspot_contact_id,
                body=f"STOP received — outreach deactivated",
                direction="INBOUND",
                trace_id=trace_id,
            )
        return {"action": "deactivated", "trace_id": trace_id}

    if is_booking_intent(message_text):
        slots = await get_available_slots(days_ahead=5)
        if slots:
            # Book the first available slot automatically if prospect confirms
            booking = await create_booking(
                prospect_name=prospect.name,
                prospect_email=prospect.email,
                start_utc=slots[0]["utc_datetime"],
                company_name=prospect.company_name,
                icp_segment=prospect.hiring_signal_brief.icp_segment.value if prospect.hiring_signal_brief else "",
                trace_id=trace_id,
            )
            if booking.get("uid"):
                prospect.discovery_call_booked = True
                prospect.calcom_booking_uid = booking["uid"]
                if prospect.hubspot_contact_id:
                    await mark_discovery_call_booked(prospect.hubspot_contact_id, booking["uid"])

            sms_body = f"Booked! You'll get a calendar invite at {prospect.email}. Talk soon."
        else:
            sms_body = "Let me check availability — I'll send you a calendar link shortly."

        send_result = await send_sms(
            to_number=prospect.phone or settings.staff_sink_sms,
            message=sms_body,
            trace_id=trace_id,
        )
        if prospect.hubspot_contact_id:
            await log_sms_activity(
                prospect.hubspot_contact_id,
                body=sms_body,
                direction="OUTBOUND",
                trace_id=trace_id,
            )
        return {"action": "booking_sent", "trace_id": trace_id, "send_result": send_result}

    # General reply via LLM (keep SMS to 160 chars)
    conversation = [
        {"role": "system", "content": SYSTEM_PROMPT + "\nIMPORTANT: Reply is via SMS. Max 160 characters."},
        {
            "role": "user",
            "content": f"Prospect SMS: {message_text}\nContext: {prospect.company_name}, {prospect.title}",
        },
    ]
    reply_text = await _llm_reply(conversation, trace_id)
    reply_text = reply_text[:160]

    send_result = await send_sms(
        to_number=prospect.phone or settings.staff_sink_sms,
        message=reply_text,
        trace_id=trace_id,
    )
    if prospect.hubspot_contact_id:
        await log_sms_activity(
            prospect.hubspot_contact_id,
            body=reply_text,
            direction="OUTBOUND",
            trace_id=trace_id,
        )

    return {"action": "sms_reply_sent", "trace_id": trace_id, "send_result": send_result}
