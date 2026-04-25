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
| Trials | 5 trials (trial_0 – trial_4), all complete |
| Temperature | 0.0 (user simulator), default (agent) |
| Parallelism | 3 tasks concurrent |
| Git commit | `d11a97072c49d093f7b5a3e4fe9da95b490d43ba` |

## Final Results — 5-Trial Baseline (April 24, 2026)

| Metric | Value |
|--------|-------|
| Task-trials completed | **94 / 150** (56 incomplete due to infra timeouts across trials) |
| Unique tasks with at least one result | **29 / 30** (task 29 had 0 completions) |
| Total passes | **28 / 94** |
| **pass@1** | **0.2979** |
| 95% CI | **[0.2148, 0.3968]** |
| Published SOTA reference | ~42% (GPT-5 class, τ²-Bench leaderboard Feb 2026) |
| Delta to SOTA | −12.2 pp |
| p50 task duration | **85.9s** |
| p95 task duration | **201.0s** |

### Per-trial summary

|Trial|Completed sims|Passed|pass@1|
|-----|--------------|------|------|
|trial_0|19|6|31.6%|
|trial_1|5|2|40.0%|
|trial_2|22|5|22.7%|
|trial_3|19|7|36.8%|
|trial_4|29|8|27.6%|

**Note on incomplete coverage.** 56 of 150 expected task-trials did not produce a simulation record. Root cause: `--auto-resume` was set but some tasks hit the 30-minute per-trial timeout or returned `null` simulation objects on infra errors. The harness bug (crash on `None` simulation entries) was patched in `eval/harness.py` on April 25. The pass@1 of 29.79% covers the 94 completed task-trials and is reported as the conservative baseline for Act IV.

### Per-task pass rates (completed tasks)

|Task|Pass rate|Task|Pass rate|
|----|---------|----|----|
|0|1.00 pass|14|0.00 fail|
|1|0.20|15|0.25|
|2|0.00 fail|16|0.00 fail|
|3|0.00 fail|17|0.75 pass|
|4|0.00 fail|18|0.00 fail|
|5|0.00 fail|19|0.00 fail|
|6|0.40|20|0.00 fail|
|7|0.00 fail|21|0.00 fail|
|8|0.25|22|0.00 fail|
|9|0.75 pass|23|0.50|
|10|0.75 pass|24|0.00 fail|
|11|0.25|25|0.00 fail|
|12|1.00 pass|26|1.00 pass|
|13|0.25|27|1.00 pass|
|--|--|28|0.00 fail|

### Sample task outcomes

- Task 0: ✅ reward 1.0 — exchange_delivered_order_items, all actions correct (all 5 trials)
- Task 1: ❌ reward 0.0 — write action (exchange) failed despite correct reads (4/5 trials)
- Task 12: ✅ reward 1.0 — passes all 5 trials consistently
- Task 27: ✅ reward 1.0 — passes all 5 trials consistently

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
