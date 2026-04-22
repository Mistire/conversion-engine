"""
End-to-end test with a synthetic prospect.
Measures latency across the full pipeline and prints results.

Usage:
  cd conversion-engine
  source .venv/bin/activate
  python scripts/test_e2e.py
"""
import asyncio
import json
import time
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from agent.models import ProspectContact
from agent.agent import initiate_outreach, handle_email_reply

# ─── Synthetic prospects (generated from Crunchbase firmographics + fictitious contacts) ────

SYNTHETIC_PROSPECTS = [
    ProspectContact(
        name="Alex Chen",
        email="alex.chen@synthcorp-a.io",
        phone="+251911000001",
        title="CTO",
        company_name="Shopify",
        company_domain="shopify.com",
    ),
    ProspectContact(
        name="Maria Santos",
        email="maria.santos@synthcorp-b.io",
        phone="+251911000002",
        title="VP Engineering",
        company_name="Stripe",
        company_domain="stripe.com",
    ),
    ProspectContact(
        name="James Park",
        email="james.park@synthcorp-c.io",
        phone="+251911000003",
        title="Head of AI",
        company_name="Figma",
        company_domain="figma.com",
    ),
    ProspectContact(
        name="Priya Patel",
        email="priya.patel@synthcorp-d.io",
        phone="+251911000004",
        title="Co-Founder & CEO",
        company_name="OpenAI",
        company_domain="openai.com",
    ),
    ProspectContact(
        name="David Kim",
        email="david.kim@synthcorp-e.io",
        phone="+251911000005",
        title="VP Product",
        company_name="Notion",
        company_domain="notion.so",
    ),
]

SYNTHETIC_REPLIES = [
    "Thanks for reaching out. Can you tell me more about your bench capacity for Python/ML engineers?",
    "Interesting. We're actually in the middle of a hiring freeze — is this still relevant?",
    "I'd be open to a quick call. What times work next week?",
    "We already work with another offshore vendor. Why Tenacious?",
    "Not sure this is a fit right now but feel free to follow up in Q3.",
]


async def run_test():
    results = []
    latencies_ms = []

    print("=" * 65)
    print("Tenacious Conversion Engine — End-to-End Test (Synthetic Prospects)")
    print("=" * 65)
    print(f"\nTesting {len(SYNTHETIC_PROSPECTS)} synthetic prospects...\n")

    for i, prospect in enumerate(SYNTHETIC_PROSPECTS):
        print(f"[{i+1}/{len(SYNTHETIC_PROSPECTS)}] {prospect.name} @ {prospect.company_name}")

        t_start = time.monotonic()
        result = await initiate_outreach(prospect)
        latency_ms = int((time.monotonic() - t_start) * 1000)
        latencies_ms.append(latency_ms)

        print(f"  ICP Segment: {result['icp_segment']}")
        print(f"  AI Maturity: {result['ai_maturity']}/3")
        print(f"  Email variant: {result['variant']}")
        print(f"  Latency: {latency_ms}ms")
        print(f"  HubSpot ID: {result.get('hubspot_contact_id', 'N/A')}")
        print(f"  Routed to sink: {result.get('send_result', {}).get('routed_to_sink', True)}")
        print()

        results.append({
            "prospect": prospect.name,
            "company": prospect.company_name,
            "icp_segment": result["icp_segment"],
            "ai_maturity": result["ai_maturity"],
            "variant": result["variant"],
            "latency_ms": latency_ms,
            "trace_id": result["trace_id"],
        })

    # Test email reply handling (4 more prospects → simulated replies)
    print("─" * 65)
    print("Testing email reply handling...\n")

    reply_prospects = SYNTHETIC_PROSPECTS[:4]
    for i, (prospect, reply) in enumerate(zip(reply_prospects, SYNTHETIC_REPLIES)):
        t_start = time.monotonic()
        reply_result = await handle_email_reply(
            prospect=prospect,
            reply_text=reply,
            subject="Re: Engineering capacity for " + prospect.company_name,
        )
        latency_ms = int((time.monotonic() - t_start) * 1000)
        latencies_ms.append(latency_ms)

        print(f"[{i+1}] Reply from {prospect.name}: \"{reply[:60]}...\"")
        print(f"  Agent variant: {reply_result.get('variant', 'N/A')} | Latency: {latency_ms}ms\n")

        results.append({
            "prospect": prospect.name,
            "company": prospect.company_name,
            "event": "email_reply_handled",
            "variant": reply_result.get("variant"),
            "latency_ms": latency_ms,
            "trace_id": reply_result.get("trace_id"),
        })

    # Compute latency stats
    sorted_lat = sorted(latencies_ms)
    n = len(sorted_lat)
    p50 = sorted_lat[n // 2]
    p95 = sorted_lat[int(n * 0.95)]
    avg = sum(sorted_lat) / n

    print("=" * 65)
    print(f"Latency across {n} interactions:")
    print(f"  p50: {p50}ms")
    print(f"  p95: {p95}ms")
    print(f"  avg: {avg:.0f}ms")
    print()

    # Save results
    output = {
        "total_interactions": n,
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
        "avg_latency_ms": round(avg, 1),
        "results": results,
    }
    output_path = ROOT / "eval" / "e2e_test_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Results saved to {output_path}")
    print("=" * 65)

    return output


if __name__ == "__main__":
    asyncio.run(run_test())
