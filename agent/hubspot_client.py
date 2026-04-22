"""
HubSpot CRM integration via REST API (MCP-compatible).
Every conversation event is written back to HubSpot.
Rate limit: 100 API calls per 10 seconds.
"""
import json
from datetime import datetime
from typing import Optional

import httpx

from agent.config import get_settings
from agent.models import HiringSignalBrief, CompetitorGapBrief, ICPSegment, ProspectContact

settings = get_settings()
HUBSPOT_BASE = "https://api.hubapi.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.hubspot_access_token}",
        "Content-Type": "application/json",
    }


# ─── Contacts ─────────────────────────────────────────────────────────────────

async def upsert_contact(prospect: ProspectContact) -> Optional[str]:
    """
    Create or update a HubSpot contact. Returns contact_id.
    All enrichment fields are written as custom properties.
    """
    if not settings.hubspot_access_token:
        return f"mock_contact_{prospect.email.replace('@', '_at_')}"

    brief = prospect.hiring_signal_brief
    gap = prospect.competitor_gap_brief

    properties = {
        "email": prospect.email,
        "firstname": prospect.name.split()[0] if prospect.name else "",
        "lastname": " ".join(prospect.name.split()[1:]) if len(prospect.name.split()) > 1 else "",
        "phone": prospect.phone or "",
        "jobtitle": prospect.title,
        "company": prospect.company_name,
        "website": prospect.company_domain,
        # Tenacious-specific enrichment fields
        "tenacious_icp_segment": brief.icp_segment.value if brief else "unknown",
        "tenacious_icp_confidence": brief.icp_confidence.value if brief else "low",
        "tenacious_ai_maturity_score": str(brief.ai_maturity.score if brief and brief.ai_maturity else 0),
        "tenacious_crunchbase_id": brief.crunchbase_id if brief else "",
        "tenacious_sector": brief.sector if brief else "",
        "tenacious_signal_brief_json": json.dumps(brief.model_dump() if brief else {}),
        "tenacious_gap_brief_json": json.dumps(gap.model_dump() if gap else {}),
        "tenacious_enrichment_timestamp": datetime.utcnow().isoformat(),
        "tenacious_email_thread_active": str(prospect.email_thread_active).lower(),
        "tenacious_sms_thread_active": str(prospect.sms_thread_active).lower(),
        "tenacious_discovery_call_booked": str(prospect.discovery_call_booked).lower(),
    }

    # Try update first (search by email)
    async with httpx.AsyncClient(timeout=15.0) as client:
        search_resp = await client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/search",
            headers=_headers(),
            json={"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": prospect.email}]}]},
        )
        if search_resp.status_code == 200:
            results = search_resp.json().get("results", [])
            if results:
                contact_id = results[0]["id"]
                await client.patch(
                    f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}",
                    headers=_headers(),
                    json={"properties": properties},
                )
                return contact_id

        # Create new contact
        create_resp = await client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
            headers=_headers(),
            json={"properties": properties},
        )
        if create_resp.status_code in (200, 201):
            return create_resp.json().get("id")

    return None


async def log_email_activity(
    contact_id: str,
    subject: str,
    body: str,
    direction: str = "OUTBOUND",
    trace_id: Optional[str] = None,
) -> Optional[str]:
    """Log an email activity/engagement to a HubSpot contact."""
    if not settings.hubspot_access_token:
        return f"mock_email_activity_{trace_id or 'test'}"

    payload = {
        "engagement": {"active": True, "type": "EMAIL", "timestamp": int(datetime.utcnow().timestamp() * 1000)},
        "associations": {"contactIds": [int(contact_id)]},
        "metadata": {
            "from": {"email": settings.resend_from_email},
            "subject": subject,
            "html": body,
            "direction": direction,
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{HUBSPOT_BASE}/engagements/v1/engagements",
            headers=_headers(),
            json=payload,
        )
        if resp.status_code in (200, 201):
            return str(resp.json().get("engagement", {}).get("id", ""))
    return None


async def log_sms_activity(
    contact_id: str,
    body: str,
    direction: str = "OUTBOUND",
    trace_id: Optional[str] = None,
) -> Optional[str]:
    """Log an SMS activity as a note on the HubSpot contact."""
    if not settings.hubspot_access_token:
        return f"mock_sms_activity_{trace_id or 'test'}"

    note_body = f"[SMS {direction}] {body}\n\nTrace: {trace_id or 'n/a'}"
    payload = {
        "engagement": {"active": True, "type": "NOTE", "timestamp": int(datetime.utcnow().timestamp() * 1000)},
        "associations": {"contactIds": [int(contact_id)]},
        "metadata": {"body": note_body},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{HUBSPOT_BASE}/engagements/v1/engagements",
            headers=_headers(),
            json=payload,
        )
        if resp.status_code in (200, 201):
            return str(resp.json().get("engagement", {}).get("id", ""))
    return None


async def mark_discovery_call_booked(contact_id: str, calcom_booking_uid: str) -> bool:
    """Update contact to show discovery call is booked."""
    if not settings.hubspot_access_token:
        return True

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.patch(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}",
            headers=_headers(),
            json={
                "properties": {
                    "tenacious_discovery_call_booked": "true",
                    "tenacious_calcom_booking_uid": calcom_booking_uid,
                    "tenacious_enrichment_timestamp": datetime.utcnow().isoformat(),
                }
            },
        )
        return resp.status_code in (200, 204)
