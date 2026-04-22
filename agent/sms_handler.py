"""
SMS handler — Africa's Talking sandbox.
SECONDARY channel only: used for warm leads who have already replied by email
and want fast coordination around scheduling. NOT for cold outreach.

SAFETY: When live_mode=False (default), all outbound SMS goes to staff_sink_sms.
"""
from datetime import datetime
from typing import Optional

from agent.config import get_settings

settings = get_settings()

STOP_COMMANDS = {"stop", "unsubscribe", "unsub", "cancel", "end", "quit", "help"}
BOOKING_KEYWORDS = {"book", "schedule", "call", "meeting", "calendar", "time", "slot", "yes", "confirm"}


def _get_at_sms():
    """Lazy-init Africa's Talking SMS service."""
    import africastalking
    africastalking.initialize(settings.africastalking_username, settings.africastalking_api_key)
    return africastalking.SMS


async def send_sms(
    to_number: str,
    message: str,
    trace_id: Optional[str] = None,
) -> dict:
    """
    Sends SMS via Africa's Talking sandbox.
    When live_mode=False, routes to staff_sink_sms.
    Enforces 160-char limit per SMS part.
    """
    actual_to = settings.staff_sink_sms if not settings.live_mode else to_number
    routed_to_sink = not settings.live_mode

    if not settings.africastalking_api_key:
        return {
            "message_id": f"mock_sms_{trace_id or 'test'}",
            "to": actual_to,
            "routed_to_sink": routed_to_sink,
            "status": "mock_sent",
            "timestamp": datetime.utcnow().isoformat(),
        }

    text = message[:480]  # cap at 3 SMS parts
    if routed_to_sink:
        text = f"[SINK|{to_number}] {text}"

    try:
        sms = _get_at_sms()
        response = sms.send(text, [actual_to])
        recipients = response.get("SMSMessageData", {}).get("Recipients", [])
        status = recipients[0].get("status", "unknown") if recipients else "unknown"
        msg_id = recipients[0].get("messageId", "") if recipients else ""
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "to": actual_to,
            "routed_to_sink": routed_to_sink,
            "timestamp": datetime.utcnow().isoformat(),
        }

    return {
        "message_id": msg_id,
        "to": actual_to,
        "original_to": to_number,
        "routed_to_sink": routed_to_sink,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        "trace_id": trace_id or "",
    }


def handle_stop_command(from_number: str) -> dict:
    """Handle STOP/UNSUBSCRIBE — immediately deactivates outreach for this number."""
    return {
        "action": "deactivate",
        "number": from_number,
        "timestamp": datetime.utcnow().isoformat(),
        "message": "Outreach deactivated per user request. No further messages will be sent.",
    }


def is_stop_command(text: str) -> bool:
    return text.strip().lower() in STOP_COMMANDS


def is_booking_intent(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in BOOKING_KEYWORDS)


def compose_scheduling_sms(prospect_name: str, calcom_url: str) -> str:
    """Short SMS to warm lead for calendar scheduling. Under 160 chars."""
    first = prospect_name.split()[0]
    msg = f"Hi {first}, happy to find a time that works! Book directly here: {calcom_url} — takes 30 sec."
    return msg[:320]  # allow up to 2 parts


def compose_warm_followup_sms(prospect_name: str) -> str:
    first = prospect_name.split()[0]
    return f"Hi {first}, just checking in on our email thread — happy to coordinate scheduling via text if easier."
