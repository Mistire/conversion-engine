"""
Smoke test — verifies each integration connects successfully.
Does NOT use LLM credits or send real messages.

Usage:
  cd conversion-engine
  source .venv/bin/activate
  python scripts/smoke_test.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import httpx
from agent.config import get_settings

settings = get_settings()

OK   = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
SKIP = "\033[93m~\033[0m"

_all_ok = True


def result(label: str, ok: bool | None, detail: str = ""):
    global _all_ok
    sym = OK if ok is True else (SKIP if ok is None else FAIL)
    suffix = f"  {detail}" if detail else ""
    print(f"  {sym}  {label}{suffix}")
    if ok is False:
        _all_ok = False


async def check_resend():
    print("\n[1] Resend (email)")
    if not settings.resend_api_key:
        result("API key", None, "not set — skipping")
        return
    # Use the /api-keys endpoint to validate auth
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.resend.com/api-keys",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        )
    # 200 = full key, 401 with restricted_api_key = send-only key (still valid)
    restricted = r.status_code == 401 and "restricted_api_key" in r.text
    ok = r.status_code == 200 or restricted
    label = "API key valid (send-only)" if restricted else "API key valid"
    result(label, ok, f"HTTP {r.status_code}" + ("" if ok else f"  →  {r.text[:120]}"))
    result("FROM email", True, settings.resend_from_email)


async def check_africastalking():
    print("\n[2] Africa's Talking (SMS)")
    if not settings.africastalking_api_key:
        result("API key", None, "not set — skipping")
        return
    # Sandbox uses its own host; validate by fetching user data
    sandbox = settings.africastalking_username == "sandbox"
    base = "https://api.sandbox.africastalking.com" if sandbox else "https://api.africastalking.com"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{base}/version1/user",
            headers={
                "apiKey": settings.africastalking_api_key,
                "Accept": "application/json",
            },
            params={"username": settings.africastalking_username},
        )
    ok = r.status_code == 200
    result("API key valid", ok, f"HTTP {r.status_code}" + ("" if ok else f"  →  {r.text[:120]}"))
    if ok:
        data = r.json().get("UserData", {})
        result("Username", True, data.get("userName", settings.africastalking_username))
    result("Shortcode", True, settings.africastalking_shortcode)


async def check_hubspot():
    print("\n[3] HubSpot (CRM)")
    if not settings.hubspot_access_token:
        result("Access token", None, "not set — skipping")
        return
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.hubapi.com/crm/v3/objects/contacts?limit=1",
            headers={"Authorization": f"Bearer {settings.hubspot_access_token}"},
        )
    ok = r.status_code == 200
    result("Access token valid", ok, f"HTTP {r.status_code}")
    if ok:
        result("Portal ID", True, settings.hubspot_portal_id)


async def check_calcom():
    print("\n[4] Cal.com (calendar)")
    if not settings.calcom_api_key:
        result("API key", None, "not set — skipping")
        return
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(
                f"{settings.calcom_base_url}/me",
                headers={
                    "Authorization": f"Bearer {settings.calcom_api_key}",
                    "cal-api-version": "2024-08-13",
                },
            )
        ok = r.status_code == 200
        result("API key valid", ok, f"HTTP {r.status_code}")
        if ok:
            name = r.json().get("data", {}).get("name") or r.json().get("name", "")
            result("Account", True, name)
    except httpx.TimeoutException:
        result("API key valid", False, "connection timed out — check network/VPN")
    result("Event type ID", bool(settings.calcom_event_type_id), settings.calcom_event_type_id or "not set")


async def check_langfuse():
    print("\n[5] Langfuse (observability)")
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        result("Keys", None, "not set — skipping")
        return
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{settings.langfuse_host}/api/public/health")
    ok = r.status_code == 200
    result("Host reachable", ok, settings.langfuse_host)
    result("Public key", True, settings.langfuse_public_key[:16] + "...")


async def check_openrouter():
    print("\n[6] OpenRouter (LLM)")
    if not settings.openrouter_api_key:
        result("API key", None, "not set — skipping")
        return
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        )
    ok = r.status_code == 200
    result("API key valid", ok, f"HTTP {r.status_code}")
    if ok:
        data = r.json().get("data", {})
        result("Model", True, settings.openrouter_model)
        credits = data.get("limit_remaining")
        if credits is not None:
            result("Credits remaining", True, f"${credits:.4f}")


async def main():
    print("=" * 55)
    print("  Tenacious Conversion Engine — Integration Smoke Test")
    print("=" * 55)

    for check in [check_resend, check_africastalking, check_hubspot,
                  check_calcom, check_langfuse, check_openrouter]:
        try:
            await check()
        except Exception as e:
            result(f"{check.__name__} crashed", False, str(e)[:100])

    print("\n" + "=" * 55)
    if _all_ok:
        print(f"  {OK}  All integrations connected successfully")
    else:
        print(f"  {FAIL}  Some integrations failed — see above")
    print("=" * 55)

    if not _all_ok:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
