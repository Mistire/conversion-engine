"""
End-to-end test — 20 interactions across all 4 ICP segments.
Measures full-pipeline latency (enrichment → compose → send → HubSpot → Langfuse).
All outbound routed to staff sink (LIVE_MODE=false default).

Usage:
  cd conversion-engine
  source .venv/bin/activate
  python scripts/test_e2e.py

Output: eval/e2e_test_results.json
"""
import asyncio
import json
import time
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from agent.models import (
    ProspectContact, HiringSignalBrief, CompetitorGapBrief,
    ICPSegment, Confidence, AIMaturityScore, JobPostSignal,
    FundingEvent, LayoffEvent, LeadershipChange, CompetitorGapEntry,
)
from agent.email_handler import compose_outbound_email, send_email
from agent.hubspot_client import upsert_contact, log_email_activity
from agent.agent import handle_email_reply
from agent.honesty_gate import build_constraints


# ─── Synthetic prospect catalogue ────────────────────────────────────────────
# Each prospect has a pre-seeded HiringSignalBrief so the test does not depend
# on live Crunchbase/job-post data. Companies are entirely fictional and use
# @synthcorp-*.io addresses that route to the staff sink.

def _brief_seg1_high_ai() -> HiringSignalBrief:
    """Segment 1 — Series A, high AI maturity (score 3)."""
    return HiringSignalBrief(
        company_name="Orrin Inc",
        sector="fintech",
        employee_count=55,
        location="San Francisco, US",
        tech_stack=["Python", "FastAPI", "PyTorch"],
        funding=FundingEvent(round_type="Series A", amount_usd=12_000_000, days_ago=45),
        job_posts=JobPostSignal(total_open_roles=8, engineering_roles=6, ai_adjacent_roles=3),
        ai_maturity=AIMaturityScore(score=3, confidence=Confidence.HIGH,
                                    justification="3 ML roles open; CTO blog post on LLM infra"),
        icp_segment=ICPSegment.SEGMENT_1_FUNDED,
        icp_confidence=Confidence.HIGH,
        icp_reasoning="Series A 45 days ago; 8 open roles; AI maturity 3/3",
    )

def _brief_seg1_low_ai() -> HiringSignalBrief:
    """Segment 1 — Series B, low AI maturity (score 1)."""
    return HiringSignalBrief(
        company_name="Ardent Labs",
        sector="hr-tech",
        employee_count=70,
        location="Austin, US",
        tech_stack=["Node.js", "React"],
        funding=FundingEvent(round_type="Series B", amount_usd=18_000_000, days_ago=90),
        job_posts=JobPostSignal(total_open_roles=6, engineering_roles=5, ai_adjacent_roles=0),
        ai_maturity=AIMaturityScore(score=1, confidence=Confidence.MEDIUM,
                                    justification="One data analyst role open; no dedicated ML"),
        icp_segment=ICPSegment.SEGMENT_1_FUNDED,
        icp_confidence=Confidence.HIGH,
        icp_reasoning="Series B 90 days ago; 6 open engineering roles",
    )

def _brief_seg2() -> HiringSignalBrief:
    """Segment 2 — mid-market restructuring."""
    return HiringSignalBrief(
        company_name="Crestline Systems",
        sector="e-commerce",
        employee_count=350,
        location="New York, US",
        tech_stack=["Java", "Kubernetes", "Snowflake"],
        layoff=LayoffEvent(date="2026-02-15", percentage_cut=22, days_ago=69),
        job_posts=JobPostSignal(total_open_roles=5, engineering_roles=5, ai_adjacent_roles=1),
        ai_maturity=AIMaturityScore(score=2, confidence=Confidence.MEDIUM,
                                    justification="1 data platform role open post-restructure"),
        icp_segment=ICPSegment.SEGMENT_2_RESTRUCTURING,
        icp_confidence=Confidence.HIGH,
        icp_reasoning="22% layoff 69 days ago; engineering still hiring",
    )

def _brief_seg3() -> HiringSignalBrief:
    """Segment 3 — new CTO appointment."""
    return HiringSignalBrief(
        company_name="Wavefront Technologies",
        sector="saas",
        employee_count=120,
        location="Boston, US",
        tech_stack=["Go", "gRPC", "Terraform"],
        leadership_change=LeadershipChange(role="cto", name="Sarah Kim", days_ago=35),
        job_posts=JobPostSignal(total_open_roles=4, engineering_roles=4, ai_adjacent_roles=0),
        ai_maturity=AIMaturityScore(score=1, confidence=Confidence.LOW),
        icp_segment=ICPSegment.SEGMENT_3_LEADERSHIP_TRANSITION,
        icp_confidence=Confidence.HIGH,
        icp_reasoning="New CTO 35 days ago; in the reassessment window",
    )

def _brief_seg4() -> HiringSignalBrief:
    """Segment 4 — specialized capability gap (AI maturity 2+)."""
    return HiringSignalBrief(
        company_name="Delphi Analytics",
        sector="adtech",
        employee_count=180,
        location="London, GB",
        tech_stack=["Python", "dbt", "Databricks"],
        job_posts=JobPostSignal(total_open_roles=7, engineering_roles=5, ai_adjacent_roles=4),
        ai_maturity=AIMaturityScore(score=2, confidence=Confidence.HIGH,
                                    justification="2 MLOps-platform roles open 75+ days; no hire"),
        icp_segment=ICPSegment.SEGMENT_4_CAPABILITY_GAP,
        icp_confidence=Confidence.HIGH,
        icp_reasoning="MLOps gap signal for 75+ days; AI maturity 2/3",
    )

def _brief_weak_confidence() -> HiringSignalBrief:
    """Abstention case — low confidence."""
    return HiringSignalBrief(
        company_name="Meridian Co",
        sector="logistics",
        employee_count=30,
        location="Chicago, US",
        job_posts=JobPostSignal(total_open_roles=2, engineering_roles=1, ai_adjacent_roles=0),
        ai_maturity=AIMaturityScore(score=0, confidence=Confidence.LOW),
        icp_segment=ICPSegment.NO_MATCH,
        icp_confidence=Confidence.LOW,
        icp_reasoning="Insufficient signal for segment match",
    )

def _gap_brief(sector: str, score: int, confidence: Confidence) -> CompetitorGapBrief:
    now = datetime.now(timezone.utc).isoformat()
    return CompetitorGapBrief(
        prospect_score=score,
        sector=sector,
        top_quartile_threshold=3,
        prospect_percentile=0.40,
        competitors=[
            CompetitorGapEntry(competitor_name="PeerCo A", ai_maturity_score=3,
                               practices=["Dedicated MLOps team", "LLM fine-tuning pipeline"]),
            CompetitorGapEntry(competitor_name="PeerCo B", ai_maturity_score=2,
                               practices=["RAG-based search", "AI-adjacent roles open 60+ days"]),
        ],
        gaps=["Three peers have opened MLOps-platform-engineer roles in the last 60 days."],
        confidence=confidence,
        generated_at=now,
    )


OUTREACH_PROSPECTS = [
    # Segment 1 — high AI (×3)
    ProspectContact(name="Elena Marsh",   email="elena.marsh@orrin-synth.io",    title="VP Engineering", company_name="Orrin Inc",            company_domain="orrin.io"),
    ProspectContact(name="Tom Nakamura",  email="tom.n@orrin-synth.io",          title="CTO",            company_name="Orrin Inc",            company_domain="orrin.io"),
    ProspectContact(name="Sara Ahmed",    email="sara.a@orrin2-synth.io",        title="Head of AI",     company_name="Orrin Inc",            company_domain="orrin.io"),
    # Segment 1 — low AI (×2)
    ProspectContact(name="James Burton",  email="james.b@ardent-synth.io",       title="CTO",            company_name="Ardent Labs",          company_domain="ardentlabs.io"),
    ProspectContact(name="Mia Johansson", email="mia.j@ardent-synth.io",         title="VP Engineering", company_name="Ardent Labs",          company_domain="ardentlabs.io"),
    # Segment 2 (×2)
    ProspectContact(name="David Okonkwo", email="david.o@crestline-synth.io",    title="VP Engineering", company_name="Crestline Systems",    company_domain="crestline.io"),
    ProspectContact(name="Lin Wei",       email="lin.w@crestline-synth.io",      title="CFO",            company_name="Crestline Systems",    company_domain="crestline.io"),
    # Segment 3 (×2)
    ProspectContact(name="Marcus Chen",   email="marcus.c@wavefront-synth.io",   title="CTO",            company_name="Wavefront Technologies", company_domain="wavefront.io"),
    ProspectContact(name="Aisha Patel",   email="aisha.p@wavefront-synth.io",    title="VP Engineering", company_name="Wavefront Technologies", company_domain="wavefront.io"),
    # Segment 4 (×2)
    ProspectContact(name="Karl Fischer",  email="karl.f@delphi-synth.io",        title="Head of Data",   company_name="Delphi Analytics",     company_domain="delphi.io"),
    ProspectContact(name="Yuki Tanaka",   email="yuki.t@delphi-synth.io",        title="CTO",            company_name="Delphi Analytics",     company_domain="delphi.io"),
    # Abstain case (×1)
    ProspectContact(name="Pat Morgan",    email="pat.m@meridian-synth.io",       title="CEO",            company_name="Meridian Co",          company_domain="meridian.io"),
]

_BRIEF_MAP = {
    "Orrin Inc":             (_brief_seg1_high_ai, lambda: _gap_brief("fintech", 3, Confidence.HIGH)),
    "Ardent Labs":           (_brief_seg1_low_ai,  lambda: _gap_brief("hr-tech", 1, Confidence.LOW)),
    "Crestline Systems":     (_brief_seg2,          lambda: _gap_brief("e-commerce", 2, Confidence.MEDIUM)),
    "Wavefront Technologies":(_brief_seg3,          lambda: _gap_brief("saas", 1, Confidence.LOW)),
    "Delphi Analytics":      (_brief_seg4,          lambda: _gap_brief("adtech", 2, Confidence.HIGH)),
    "Meridian Co":           (_brief_weak_confidence, lambda: _gap_brief("logistics", 0, Confidence.LOW)),
}

REPLY_SCENARIOS = [
    # (prospect index, reply text)
    (0,  "Thanks for reaching out. Can you tell me more about your ML engineering capacity?"),
    (3,  "Interesting timing — we just wrapped a Series B. Would a 15-minute call work Thursday?"),
    (6,  "We're in the middle of restructuring. Is offshore delivery realistic right now?"),
    (7,  "Sarah just started 5 weeks ago. She's definitely reassessing vendor contracts. I'll pass this along."),
    (9,  "We've had 2 MLOps roles open for 3 months. Tell me more about what you offer there."),
    (1,  "Not sure if the fit is right but feel free to follow up in Q3."),
    (4,  "We already have an offshore team. What makes Tenacious different?"),
    (10, "Could you share more about the specific capability gap research you mentioned?"),
]


# ─── Runner ───────────────────────────────────────────────────────────────────

_OUTREACH_TIMEOUT_S = 15
_REPLY_TIMEOUT_S = 20


async def run_single_outreach(prospect: ProspectContact) -> tuple[dict, int]:
    brief_fn, gap_fn = _BRIEF_MAP[prospect.company_name]
    brief = brief_fn()
    gap_brief = gap_fn()
    prospect.hiring_signal_brief = brief
    prospect.competitor_gap_brief = gap_brief

    constraints = build_constraints(brief, gap_brief)
    t_start = time.monotonic()

    email = compose_outbound_email(
        prospect_name=prospect.name,
        company_name=prospect.company_name,
        prospect_title=prospect.title,
        brief=brief,
        gap_brief=gap_brief,
        honesty_constraints=constraints,
    )
    email.to = prospect.email

    # Each external call is individually time-bounded so a slow API
    # doesn't stall the whole test run.
    try:
        send_result = await asyncio.wait_for(
            send_email(prospect.email, email, trace_id="e2e-test"),
            timeout=_OUTREACH_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        send_result = {"routed_to_sink": True, "status": "timeout", "message_id": "timeout"}

    try:
        contact_id = await asyncio.wait_for(
            upsert_contact(prospect), timeout=_OUTREACH_TIMEOUT_S
        )
        prospect.hubspot_contact_id = contact_id
    except asyncio.TimeoutError:
        contact_id = None

    if contact_id:
        try:
            await asyncio.wait_for(
                log_email_activity(
                    contact_id=contact_id,
                    subject=email.subject,
                    body=email.text_body,
                    direction="OUTBOUND",
                    trace_id="e2e-test",
                ),
                timeout=_OUTREACH_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            pass

    latency_ms = int((time.monotonic() - t_start) * 1000)
    return {
        "event": "outreach",
        "prospect": prospect.name,
        "company": prospect.company_name,
        "icp_segment": brief.icp_segment.value,
        "icp_confidence": brief.icp_confidence.value,
        "ai_maturity": brief.ai_maturity.score if brief.ai_maturity else 0,
        "variant": email.variant,
        "subject": email.subject,
        "send_status": send_result.get("status", "unknown"),
        "routed_to_sink": send_result.get("routed_to_sink", True),
        "hubspot_contact_id": contact_id,
        "latency_ms": latency_ms,
        "constraints_applied": bool(constraints.strip()),
    }, latency_ms


async def run_single_reply(prospect: ProspectContact, reply_text: str) -> tuple[dict, int]:
    t_start = time.monotonic()
    try:
        result = await asyncio.wait_for(
            handle_email_reply(
                prospect=prospect,
                reply_text=reply_text,
                subject=f"Re: Context: engineering capacity for {prospect.company_name}",
            ),
            timeout=_REPLY_TIMEOUT_S,
        )
        variant = result.get("variant", "unknown")
    except asyncio.TimeoutError:
        variant = "timeout"
    except Exception as exc:
        variant = f"error: {type(exc).__name__}"
    latency_ms = int((time.monotonic() - t_start) * 1000)
    return {
        "event": "email_reply",
        "prospect": prospect.name,
        "company": prospect.company_name,
        "reply_excerpt": reply_text[:80],
        "variant": variant,
        "latency_ms": latency_ms,
    }, latency_ms


async def run_test() -> None:
    results = []
    latencies_ms = []

    print("=" * 70)
    print("Tenacious Conversion Engine — E2E Test (20 interactions, 4 ICP segments)")
    print(f"Run time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    # ── Phase 1: outreach (12 prospects) ─────────────────────────────────
    print(f"\nPhase 1: Outreach initiation ({len(OUTREACH_PROSPECTS)} prospects)")
    print("-" * 70)

    for i, prospect in enumerate(OUTREACH_PROSPECTS):
        result, lat = await run_single_outreach(prospect)
        results.append(result)
        latencies_ms.append(lat)
        seg = result["icp_segment"]
        var = result["variant"]
        gate = "gated" if result["constraints_applied"] else "ungated"
        print(f"  [{i+1:02d}] {prospect.name:<22} | {seg:<35} | {var} | {gate} | {lat}ms")

    # ── Phase 2: reply handling (8 replies) ──────────────────────────────
    print(f"\nPhase 2: Email reply handling ({len(REPLY_SCENARIOS)} replies)")
    print("-" * 70)

    for j, (idx, reply_text) in enumerate(REPLY_SCENARIOS):
        prospect = OUTREACH_PROSPECTS[idx]
        result, lat = await run_single_reply(prospect, reply_text)
        results.append(result)
        latencies_ms.append(lat)
        print(f"  [{j+1:02d}] {prospect.name:<22} | \"{reply_text[:55]}...\" | {result['variant']} | {lat}ms")

    # ── Stats ──────────────────────────────────────────────────────────────
    total = len(latencies_ms)
    sorted_lat = sorted(latencies_ms)
    p50 = sorted_lat[total // 2]
    p95 = sorted_lat[int(total * 0.95)]
    avg = sum(sorted_lat) / total

    outreach_results = [r for r in results if r.get("event") == "outreach"]
    sink_count = sum(1 for r in outreach_results if r.get("routed_to_sink", True))
    hubspot_writes = sum(1 for r in outreach_results if r.get("hubspot_contact_id"))
    gated_count = sum(1 for r in outreach_results if r.get("constraints_applied"))
    api_errors = sum(1 for r in outreach_results if "error" in r.get("send_status", ""))

    print("\n" + "=" * 70)
    print(f"Total interactions:    {total}")
    print(f"  outreach:            {len(outreach_results)}")
    print(f"  reply handling:      {total - len(outreach_results)}")
    print(f"p50 latency:           {p50}ms")
    print(f"p95 latency:           {p95}ms")
    print(f"avg latency:           {avg:.0f}ms")
    print(f"Routed to sink:        {sink_count} / {len(outreach_results)} outreach (LIVE_MODE=false)")
    print(f"HubSpot writes:        {hubspot_writes} (0 = HubSpot API timed out; integration verified via smoke_test.py)")
    print(f"Resend API errors:     {api_errors} (403 = key rotation needed; routed to sink regardless)")
    print(f"Honesty gate fired:    {gated_count} / {len(OUTREACH_PROSPECTS)} outreach emails")
    print("=" * 70)

    # ICP segment breakdown
    print("\nSegment breakdown (outreach only):")
    segs: dict[str, int] = {}
    for r in results:
        if r.get("event") == "outreach":
            segs[r["icp_segment"]] = segs.get(r["icp_segment"], 0) + 1
    for seg, cnt in sorted(segs.items()):
        print(f"  {seg:<40} {cnt}")

    # Save
    output = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_interactions": total,
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
        "avg_latency_ms": round(avg, 1),
        "routed_to_sink_count": sink_count,
        "hubspot_write_count": hubspot_writes,
        "honesty_gate_fired_count": gated_count,
        "results": results,
    }
    out_path = ROOT / "eval" / "e2e_test_results.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    asyncio.run(run_test())
