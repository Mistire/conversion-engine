"""
FastAPI app — webhook endpoints for email and SMS inbound,
plus REST endpoints for triggering outreach.
"""
import json
import time
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent.config import get_settings
from agent.models import ProspectContact
from agent.agent import initiate_outreach, handle_email_reply, handle_sms_inbound

settings = get_settings()
app = FastAPI(title="Tenacious Conversion Engine", version="0.1.0")

# In-memory prospect store (replace with DB for production)
_prospects: dict[str, ProspectContact] = {}


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "live_mode": settings.live_mode,
        "timestamp": datetime.utcnow().isoformat(),
        "warning": None if settings.live_mode else "LIVE_MODE=false — all outbound routed to staff sink",
    }


# ─── Outreach trigger ─────────────────────────────────────────────────────────

class OutreachRequest(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    title: str = ""
    company_name: str
    company_domain: str = ""


@app.post("/outreach/initiate")
async def initiate(req: OutreachRequest):
    """
    Trigger full outreach pipeline for a single prospect.
    Enriches → classifies → composes → sends → logs to HubSpot.
    """
    t_start = time.monotonic()
    prospect = ProspectContact(**req.model_dump())

    result = await initiate_outreach(prospect)

    # Cache prospect for follow-up webhook handling
    _prospects[prospect.email] = prospect

    result["latency_ms"] = int((time.monotonic() - t_start) * 1000)
    return result


# ─── Email reply webhook ──────────────────────────────────────────────────────

@app.post("/webhooks/email")
async def email_webhook(request: Request):
    """
    Receives email reply events from Resend/MailerSend webhook.
    Expects JSON payload with: from_email, subject, text_body.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    from_email = payload.get("from") or payload.get("from_email") or ""
    subject = payload.get("subject") or ""
    text_body = payload.get("text") or payload.get("text_body") or payload.get("body") or ""

    if not from_email or not text_body:
        return JSONResponse({"status": "ignored", "reason": "missing fields"})

    prospect = _prospects.get(from_email)
    if not prospect:
        # Unknown sender — create minimal prospect record
        prospect = ProspectContact(
            name=from_email.split("@")[0].capitalize(),
            email=from_email,
            company_name=from_email.split("@")[-1].split(".")[0].capitalize(),
        )
        _prospects[from_email] = prospect

    t_start = time.monotonic()
    result = await handle_email_reply(prospect, text_body, subject)
    result["latency_ms"] = int((time.monotonic() - t_start) * 1000)

    return result


# ─── SMS inbound webhook ──────────────────────────────────────────────────────

@app.post("/webhooks/sms")
async def sms_webhook(request: Request):
    """
    Receives inbound SMS from Africa's Talking webhook.
    Expects form-encoded: from, text, to (Africa's Talking format).
    """
    try:
        form = await request.form()
        from_number = str(form.get("from") or "")
        text = str(form.get("text") or "")
        to_number = str(form.get("to") or "")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid form data")

    if not from_number or not text:
        return JSONResponse({"status": "ignored"})

    # Look up prospect by phone number
    prospect = next((p for p in _prospects.values() if p.phone == from_number), None)
    if not prospect:
        prospect = ProspectContact(
            name=from_number,
            email=f"{from_number.lstrip('+')}@unknown.sms",
            phone=from_number,
            company_name="Unknown",
        )
        _prospects[from_number] = prospect

    result = await handle_sms_inbound(prospect, text)
    return result


# ─── Status endpoints ─────────────────────────────────────────────────────────

@app.get("/prospects")
async def list_prospects():
    return {
        "count": len(_prospects),
        "prospects": [
            {
                "email": p.email,
                "company": p.company_name,
                "icp_segment": p.hiring_signal_brief.icp_segment.value if p.hiring_signal_brief else "not_enriched",
                "email_thread_active": p.email_thread_active,
                "discovery_call_booked": p.discovery_call_booked,
            }
            for p in _prospects.values()
        ],
    }


@app.get("/prospects/{email}")
async def get_prospect(email: str):
    prospect = _prospects.get(email)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return prospect.model_dump()
