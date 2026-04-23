# Act I Baseline — τ²-Bench Retail Domain

## What Was Reproduced

Cloned `sierra-research/tau2-bench` (τ²-bench, v1.0.0, April 2026) and verified the `retail` domain loads successfully with the τ²-bench CLI (`tau2 run`). The harness wrapper in `eval/harness.py` wraps the CLI, writes per-task trace records to `eval/trace_log.jsonl`, and appends scored run entries to `eval/score_log.json`.

The dev slice is defined as task IDs 0–29 (30 tasks); the sealed held-out slice is 30–49 (20 tasks).

## Baseline Configuration

| Item | Value |
|------|-------|
| Model | `qwen/qwen3-235b-a22b` via OpenRouter (dev tier) |
| Domain | `retail` |
| Slice | dev (30 tasks) |
| Trials | 5-trial pass@1 (trial 0 complete at interim submission; trials 1–4 in progress) |
| Temperature | 0.0 (user simulator), default (agent) |
| Parallelism | 3 tasks concurrent |

## Results (Trial 0 — 19/30 tasks at interim submission)

| Metric | Value |
|--------|-------|
| Tasks completed | 19 / 30 |
| Tasks passed | 6 / 19 |
| pass@1 (trial 0, partial) | **31.6%** |
| Published SOTA reference | ~42% (GPT-5 class, τ²-Bench leaderboard Feb 2026) |
| Delta to SOTA | −10.4 pp (expected for dev-tier model) |
| p50 task duration | 93s |
| p95 task duration | 677s |

Full 5-trial pass@1 with 95% CI will be available in the final submission (Saturday April 25).

### Sample task outcomes

- Task 0: ✅ reward 1.0 — exchange_delivered_order_items, all actions correct
- Task 1: ❌ reward 0.0 — write action (exchange) failed despite correct reads

## Production Stack End-to-End Test

All 6 integrations verified via `scripts/smoke_test.py`:

| Service | Status |
|---------|--------|
| Resend (email) | ✅ send-only key valid, FROM: onboarding@resend.dev |
| Africa's Talking (SMS) | ✅ sandbox, shortcode 73577 |
| HubSpot CRM | ✅ portal 245993570 |
| Cal.com | ✅ cloud API, event type 5470140, account: Mistire Daniel |
| Langfuse | ✅ cloud.langfuse.com connected |
| OpenRouter | ✅ $18.57 credits remaining |

The `scripts/test_e2e.py` script runs 9 interactions (5 outreach initiations + 4 reply handlings) against synthetic prospects. All interactions run with `LIVE_MODE=false`, routing outbound to the staff sink.

| Metric | Value |
|--------|-------|
| p50 latency | 608 ms |
| p95 latency | 936 ms |
| Interactions tested | 9 |
| Routed to staff sink | 100% (LIVE_MODE=false) |
| HubSpot writes | Live (portal 245993570) |
| Cal.com bookings | Live (event type 5470140) |

## Unexpected Behavior

The Crunchbase ODM sample does not include large public companies (Shopify, Stripe, etc.) used in the synthetic test — ICP classification defaults to `no_match` for these, and the agent correctly falls back to generic pitch language rather than hallucinating firmographics.

LiteLLM cost tracking logs `$0.0000` per task because the model version string `qwen/qwen3-235b-a22b-04-28` (date-stamped by OpenRouter) is not in LiteLLM's pricing table. Actual spend is tracked via the OpenRouter dashboard.

## Cost Per Evaluation Run (Estimated)

| Item | Estimate |
|------|----------|
| LLM cost per τ²-Bench task (dev tier) | ~$0.02–0.05 |
| 5 trials × 30 tasks | ~$3–7.50 |
| Target budget Days 1–4 | ≤ $4 |
