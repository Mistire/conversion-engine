"""
Channel routing state machine — Tenacious Conversion Engine.

Implements the three-channel hierarchy explicitly:
  EMAIL (primary)  →  SMS (secondary, warm leads only)  →  VOICE (discovery call)

Key exports:
  ChannelState      — explicit state enum for a prospect's position in the pipeline
  ProspectChannel   — per-prospect state container
  WarmLeadGate      — blocks SMS until the prospect has replied by email
  generate_calcom_link() — single source of truth for Cal.com booking links,
                           imported by both email_handler and sms_handler

Channel rules (from seed/style_guide.md and agent spec):
  - Email is the ONLY cold-outreach channel. Never send cold SMS or cold voice.
  - SMS activates only after a prospect replies by email (warm gate).
  - SMS is used for scheduling coordination only — max 3 messages, 160 chars each.
  - Voice = booked discovery call delivered by a human delivery lead. Agent books it;
    human attends. The agent never initiates cold voice outreach.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── State machine ────────────────────────────────────────────────────────────

class ChannelState(str, Enum):
    """
    Pipeline positions for a prospect. Transitions are one-way except for
    OPTED_OUT (terminal) and THREAD_CLOSED (terminal).

    Allowed transitions:
      COLD → EMAIL_SENT → EMAIL_REPLIED → CALL_BOOKING_OFFERED → CALL_BOOKED
                       ↘ SMS_ACTIVE ↗
      Any state → OPTED_OUT (on STOP / unsubscribe)
      Any state → THREAD_CLOSED (on 3-touch limit or manual close)
    """
    COLD                  = "cold"
    EMAIL_SENT            = "email_sent"
    EMAIL_REPLIED         = "email_replied"    # warm — SMS now unlocked
    SMS_ACTIVE            = "sms_active"       # warm lead on SMS coordination
    CALL_BOOKING_OFFERED  = "call_booking_offered"
    CALL_BOOKED           = "call_booked"      # terminal (success)
    OPTED_OUT             = "opted_out"        # terminal (do not contact)
    THREAD_CLOSED         = "thread_closed"    # terminal (3-touch limit or explicit close)


# Valid forward transitions — anything not listed here is a policy violation.
_VALID_TRANSITIONS: dict[ChannelState, set[ChannelState]] = {
    ChannelState.COLD:                 {ChannelState.EMAIL_SENT, ChannelState.OPTED_OUT},
    ChannelState.EMAIL_SENT:           {ChannelState.EMAIL_REPLIED, ChannelState.OPTED_OUT, ChannelState.THREAD_CLOSED},
    ChannelState.EMAIL_REPLIED:        {ChannelState.SMS_ACTIVE, ChannelState.CALL_BOOKING_OFFERED, ChannelState.OPTED_OUT},
    ChannelState.SMS_ACTIVE:           {ChannelState.CALL_BOOKING_OFFERED, ChannelState.OPTED_OUT},
    ChannelState.CALL_BOOKING_OFFERED: {ChannelState.CALL_BOOKED, ChannelState.OPTED_OUT, ChannelState.THREAD_CLOSED},
    ChannelState.CALL_BOOKED:          set(),   # terminal
    ChannelState.OPTED_OUT:            set(),   # terminal
    ChannelState.THREAD_CLOSED:        set(),   # terminal
}


class ProspectChannel(BaseModel):
    """
    Tracks the channel state and history for a single prospect.
    Stored in-process and reflected in HubSpot via tenacious_channel_state.
    """
    prospect_email: str
    state: ChannelState = ChannelState.COLD
    email_touch_count: int = 0          # max 3 within 30 days
    sms_touch_count: int = 0            # max 3 total per warm lead
    last_email_sent_at: Optional[str] = None   # ISO 8601 UTC
    last_reply_at: Optional[str] = None
    calcom_booking_uid: Optional[str] = None
    history: list[str] = Field(default_factory=list)

    def transition(self, new_state: ChannelState) -> None:
        """
        Advance state, validating the transition is permitted.
        Raises ValueError on illegal transitions (e.g., SMS to a cold prospect).
        """
        allowed = _VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Illegal channel transition: {self.state} → {new_state}. "
                f"Allowed from {self.state}: {allowed or 'none (terminal state)'}."
            )
        self.history.append(
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M UTC')}  "
            f"{self.state} → {new_state}"
        )
        self.state = new_state

    def record_email_sent(self) -> None:
        self.email_touch_count += 1
        self.last_email_sent_at = datetime.now(timezone.utc).isoformat()
        if self.state == ChannelState.COLD:
            self.transition(ChannelState.EMAIL_SENT)

    def record_email_reply(self) -> None:
        self.last_reply_at = datetime.now(timezone.utc).isoformat()
        if self.state == ChannelState.EMAIL_SENT:
            self.transition(ChannelState.EMAIL_REPLIED)

    def record_sms_sent(self) -> None:
        self.sms_touch_count += 1
        if self.state == ChannelState.EMAIL_REPLIED:
            self.transition(ChannelState.SMS_ACTIVE)

    def record_booking_offered(self) -> None:
        allowed_from = {ChannelState.EMAIL_REPLIED, ChannelState.SMS_ACTIVE}
        if self.state in allowed_from:
            self.transition(ChannelState.CALL_BOOKING_OFFERED)

    def record_call_booked(self, uid: str) -> None:
        self.calcom_booking_uid = uid
        if self.state == ChannelState.CALL_BOOKING_OFFERED:
            self.transition(ChannelState.CALL_BOOKED)

    def record_opt_out(self) -> None:
        if self.state not in {ChannelState.OPTED_OUT, ChannelState.CALL_BOOKED}:
            self.state = ChannelState.OPTED_OUT
            self.history.append(
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M UTC')}  "
                f"→ OPTED_OUT (STOP received)"
            )


# ─── Warm-lead gate ───────────────────────────────────────────────────────────

class WarmLeadGate:
    """
    SMS send gate — enforces the channel policy that SMS is secondary only.

    A prospect is warm (SMS-eligible) when they have replied to an email.
    Cold prospects — those in COLD, EMAIL_SENT — must NOT receive SMS.

    Usage:
        gate = WarmLeadGate(channel)
        if gate.allows_sms():
            await send_sms(...)
        else:
            # stay on email, do not escalate to SMS
    """
    _SMS_ELIGIBLE = {
        ChannelState.EMAIL_REPLIED,
        ChannelState.SMS_ACTIVE,
        ChannelState.CALL_BOOKING_OFFERED,
    }
    _SMS_INELIGIBLE_REASON = {
        ChannelState.COLD:         "prospect has not been contacted yet — send email first",
        ChannelState.EMAIL_SENT:   "prospect has not replied — SMS reserved for warm leads only",
        ChannelState.CALL_BOOKED:  "discovery call already booked — no further outreach needed",
        ChannelState.OPTED_OUT:    "prospect has opted out — no further contact",
        ChannelState.THREAD_CLOSED:"thread closed — reopen via email before using SMS",
    }

    def __init__(self, channel: ProspectChannel) -> None:
        self._channel = channel

    def allows_sms(self) -> bool:
        return self._channel.state in self._SMS_ELIGIBLE

    def block_reason(self) -> str:
        """Human-readable reason when allows_sms() is False."""
        return self._SMS_INELIGIBLE_REASON.get(
            self._channel.state,
            f"state {self._channel.state} is not SMS-eligible",
        )

    def sms_touch_limit_reached(self) -> bool:
        """Max 3 SMS messages per warm lead per thread."""
        return self._channel.sms_touch_count >= 3


# ─── Cal.com link generation ──────────────────────────────────────────────────

def generate_calcom_link(
    event_type_id: str,
    prefill_name: str = "",
    prefill_email: str = "",
    *,
    utm_source: str = "tenacious_outreach",
) -> str:
    """
    Single source of truth for Cal.com booking links.

    Imported by BOTH email_handler.py and sms_handler.py so the link is
    always generated identically regardless of the channel that sends it.

    Args:
        event_type_id: Cal.com event type ID (e.g. "5470140").
        prefill_name:  Prospect full name — pre-fills the booking form.
        prefill_email: Prospect email — reduces form friction.
        utm_source:    Attribution tag for Langfuse / HubSpot analytics.

    Returns:
        Full URL string, e.g.:
        https://cal.com/tenacious/discovery?name=Karl+Fischer&email=k%40delphi.io&utm_source=tenacious_outreach
    """
    from urllib.parse import quote_plus
    base = f"https://cal.com/tenacious/{event_type_id}"
    params: list[str] = []
    if prefill_name:
        params.append(f"name={quote_plus(prefill_name)}")
    if prefill_email:
        params.append(f"email={quote_plus(prefill_email)}")
    if utm_source:
        params.append(f"utm_source={quote_plus(utm_source)}")
    return base + ("?" + "&".join(params) if params else "")


def generate_calcom_link_for_email(
    prospect_name: str,
    prospect_email: str,
    event_type_id: str,
) -> str:
    """Convenience wrapper for email handler — includes name + email prefill."""
    return generate_calcom_link(
        event_type_id,
        prefill_name=prospect_name,
        prefill_email=prospect_email,
        utm_source="email_outreach",
    )


def generate_calcom_link_for_sms(
    prospect_name: str,
    prospect_email: str,
    event_type_id: str,
) -> str:
    """
    Convenience wrapper for SMS handler — shorter URL (name only, no email prefill)
    to stay within 160-char SMS limit.
    """
    return generate_calcom_link(
        event_type_id,
        prefill_name=prospect_name,
        utm_source="sms_scheduling",
    )


# ─── Channel action router ────────────────────────────────────────────────────

class ChannelRouter:
    """
    Decides the next outbound action given the current channel state.

    Called by agent.py before every outbound event to ensure channel
    policy is respected centrally rather than scattered across handlers.

    Usage:
        router = ChannelRouter(channel, settings)
        action = router.next_action(intent="booking")
        # returns "email_booking_offer" | "sms_booking_offer" | "wait" | "close"
    """

    def __init__(self, channel: ProspectChannel, event_type_id: str = "") -> None:
        self._ch = channel
        self._event_type_id = event_type_id
        self._gate = WarmLeadGate(channel)

    def next_action(self, intent: str) -> str:
        """
        intent: "booking" | "follow_up" | "reply" | "close"

        Returns an action token:
          "email_booking_offer"  — send booking slots via email
          "sms_booking_offer"    — send Cal.com link via SMS (warm leads only)
          "email_reply"          — send LLM-generated email reply
          "sms_reply"            — send LLM-generated SMS reply (warm only)
          "close_thread"         — 3-touch limit hit; close without further contact
          "no_action"            — terminal state; do nothing
          "wait"                 — too early to act (e.g. within 5-day window)
        """
        state = self._ch.state

        if state in {ChannelState.OPTED_OUT, ChannelState.CALL_BOOKED, ChannelState.THREAD_CLOSED}:
            return "no_action"

        if self._ch.email_touch_count >= 3 and state == ChannelState.EMAIL_SENT:
            return "close_thread"

        if intent == "booking":
            if self._gate.allows_sms() and not self._gate.sms_touch_limit_reached():
                return "sms_booking_offer"
            return "email_booking_offer"

        if intent == "reply":
            if state in {ChannelState.SMS_ACTIVE} and self._gate.allows_sms():
                return "sms_reply"
            return "email_reply"

        if intent == "follow_up":
            if state in {ChannelState.EMAIL_SENT, ChannelState.EMAIL_REPLIED}:
                return "email_reply"
            return "no_action"

        if intent == "close":
            return "close_thread"

        return "no_action"
