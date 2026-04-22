"""
Cal.com booking flow integration.
Self-hosted via Docker (see docker-compose.yml) or Cal.com cloud free tier.
Creates discovery call bookings — 30-minute slots with Tenacious delivery lead.
"""
import httpx
from datetime import datetime, timedelta
from typing import Optional

from agent.config import get_settings

settings = get_settings()


async def get_available_slots(days_ahead: int = 7) -> list[dict]:
    """
    Fetch available booking slots for the next N days.
    Returns list of {date, time, utc_datetime} dicts.
    """
    if not settings.calcom_api_key or not settings.calcom_event_type_id:
        # Mock slots for testing
        now = datetime.utcnow()
        slots = []
        for i in range(1, days_ahead + 1):
            day = now + timedelta(days=i)
            if day.weekday() < 5:  # Mon-Fri only
                for hour in [9, 11, 14, 16]:
                    slot_dt = day.replace(hour=hour, minute=0, second=0, microsecond=0)
                    slots.append({
                        "date": slot_dt.strftime("%Y-%m-%d"),
                        "time": slot_dt.strftime("%H:%M"),
                        "utc_datetime": slot_dt.isoformat() + "Z",
                    })
        return slots[:5]  # return first 5 available

    start = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{settings.calcom_base_url}/api/v2/slots/available",
            headers={
                "Authorization": f"Bearer {settings.calcom_api_key}",
                "cal-api-version": "2024-09-04",
            },
            params={
                "eventTypeId": settings.calcom_event_type_id,
                "startTime": start,
                "endTime": end,
            },
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        slots = []
        for date_str, times in data.get("slots", {}).items():
            for slot in times:
                slots.append({
                    "date": date_str,
                    "time": slot.get("time", ""),
                    "utc_datetime": slot.get("time", ""),
                })
        return slots[:5]


async def create_booking(
    prospect_name: str,
    prospect_email: str,
    start_utc: str,
    company_name: str,
    icp_segment: str = "",
    trace_id: Optional[str] = None,
) -> dict:
    """
    Books a 30-minute discovery call slot.
    Returns booking details with uid for HubSpot logging.
    """
    if not settings.calcom_api_key or not settings.calcom_event_type_id:
        # Mock booking for testing
        mock_uid = f"mock_booking_{prospect_email.replace('@', '_at_')}_{start_utc[:10]}"
        return {
            "uid": mock_uid,
            "status": "ACCEPTED",
            "start": start_utc,
            "attendees": [prospect_email, "delivery-lead@tenacious.io"],
            "title": f"Discovery Call — {company_name} × Tenacious",
            "mock": True,
        }

    payload = {
        "eventTypeId": int(settings.calcom_event_type_id),
        "start": start_utc,
        "attendee": {
            "name": prospect_name,
            "email": prospect_email,
            "timeZone": "UTC",
            "language": "en",
        },
        "metadata": {
            "company": company_name,
            "icp_segment": icp_segment,
            "trace_id": trace_id or "",
            "source": "tenacious_conversion_engine",
        },
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.calcom_base_url}/api/v2/bookings",
            headers={
                "Authorization": f"Bearer {settings.calcom_api_key}",
                "cal-api-version": "2024-08-13",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if resp.status_code not in (200, 201):
            return {"status": "error", "detail": resp.text}

        data = resp.json().get("data", resp.json())
        return {
            "uid": data.get("uid", ""),
            "status": data.get("status", ""),
            "start": data.get("start", start_utc),
            "title": f"Discovery Call — {company_name} × Tenacious",
            "attendees": [a.get("email") for a in data.get("attendees", [])],
        }


def format_slot_for_email(slot: dict) -> str:
    """Human-readable slot string for email body."""
    return f"{slot['date']} at {slot['time']} UTC"


def format_slots_list(slots: list[dict]) -> str:
    """Format multiple slots as a numbered list for email."""
    if not slots:
        return "Please reply with your preferred time and timezone."
    lines = [f"{i+1}. {format_slot_for_email(s)}" for i, s in enumerate(slots)]
    return "\n".join(lines)
