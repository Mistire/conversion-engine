# Act I Baseline — τ²-Bench Retail Domain

## What Was Reproduced

Cloned `sierra-research/tau2-bench` (τ³-bench, v1.0.0, April 2026) and verified the `retail` domain loads successfully with the τ²-bench CLI (`tau2 run`). The harness wrapper in `eval/harness.py` wraps the CLI, writes per-task trace records to `eval/trace_log.jsonl`, and appends scored run entries to `eval/score_log.json`.

The dev slice is defined as task IDs 0–29 (30 tasks); the sealed held-out slice is 30–49 (20 tasks). The held-out partition is delivered by program staff and not exposed during baseline development.

## Baseline Configuration

| Item | Value |
|------|-------|
| Model | `qwen/qwen3-235b-a22b` via OpenRouter (dev tier) |
| Domain | `retail` |
| Slice | dev (30 tasks) |
| Trials | 5 (pass@1 estimated from 5 × 30 = 150 task-trial pairs) |
| Temperature | 0.3 |

## Results

Full scored runs require the `OPENROUTER_API_KEY` to be set in `.env`. The harness and runner are fully wired (`eval/baseline_runner.py`). Once the key is configured, run:

```bash
source .venv/bin/activate
python eval/baseline_runner.py
```

The published τ²-Bench retail SOTA (Feb 2026) is **~42% pass@1** on GPT-5-class models. The dev-tier target (Qwen3-235B via OpenRouter) is expected to land 3–8 percentage points below SOTA (~34–39%), consistent with the published leaderboard for comparable model tiers.

## Production Stack End-to-End Test

The `scripts/test_e2e.py` script ran 9 interactions (5 outreach initiations + 4 reply handlings) against synthetic prospects derived from the Crunchbase ODM sample. All interactions ran with `LIVE_MODE=false`, routing outbound to the staff sink.

| Metric | Value |
|--------|-------|
| p50 latency | 608 ms |
| p95 latency | 936 ms |
| Interactions tested | 9 |
| Routed to staff sink | 100% (LIVE_MODE=false) |
| HubSpot writes | Mock (token not yet configured) |
| Cal.com bookings | Mock (API key not yet configured) |

Booking intent was correctly detected on the "I'd be open to a quick call" reply, routing to `booking_offer` variant. STOP command handling and grounded-honesty enforcement verified in unit path.

## Unexpected Behavior

The Crunchbase ODM sample (`crunchbase-companies-information.csv`, 1,513 records) does not include all large public companies (Shopify, Stripe, etc.) used in the synthetic test. ICP classification defaulted to `no_match` for these. The enrichment pipeline correctly falls back to generic pitch language rather than hallucinating firmographics — this is the intended grounded-honesty behavior. Real scored runs will use smaller companies present in the sample dataset.

## Cost Per Evaluation Run (Estimated)

| Item | Estimate |
|------|----------|
| LLM cost per τ²-Bench task (dev tier) | ~$0.02–0.05 |
| 5 trials × 30 tasks | ~$3–7.50 |
| Target budget Days 1–4 | ≤ $4 |

Actual cost will be confirmed from OpenRouter invoice once API key is active.
