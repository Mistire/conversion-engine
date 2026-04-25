---
title: "Tenacious Conversion Engine — Final Memo"
author: "Mistire Daniel · mistire@10academy.org · TRP1 Week 10 · 2026-04-25"
---

# Page 1 — The Decision

## Executive Summary

An automated B2B lead-generation and conversion system for Tenacious Consulting and Outsourcing was built in one week: it enriches prospects from public data, classifies them across four ICP segments, composes signal-grounded outreach, and books discovery calls via Cal.com with all six production integrations live. The Act IV honesty gate raised probe pass rate from 80% to 100% (ΔA = +20 pp) with zero additional LLM calls and sub-millisecond overhead. **Recommendation: run a 30-day pilot on Segment 1 (recently funded Series A/B) at 60 outreach/week; halt if reply rate remains below 3% after week 2.**

---

## τ²-Bench Baseline

Model `qwen/qwen3-235b-a22b` via OpenRouter (commit `d11a97072c`). 5 trials, 30-task dev slice; 94/150 task-trials completed (56 timed out, patched in `eval/harness.py`).

| Metric | Value |
|---|---|
| **pass@1** | **0.2979** [0.2148, 0.3968] 95% CI · `eval/score_log.json` |
| SOTA reference (GPT-5 class, Feb 2026) | ~0.42 · τ²-bench leaderboard |
| Delta to SOTA | −12.2 pp |
| p50 / p95 task duration | 85.9 s / 201.0 s |

The 29.79% result is below the expected 34–39% dev-tier range; incomplete coverage (94/150 simulations) is the primary cause.

---

## Cost per Qualified Lead

OpenRouter weekly spend: **$12.75** (covers τ²-Bench runs, probe suite, and 20-interaction e2e test). LLM cost attributable to lead qualification (e2e only, ~10% of total spend): **~$1.25**. 11 qualified leads processed in the e2e run. Infrastructure (Resend, Africa's Talking sandbox, HubSpot dev sandbox, Cal.com self-hosted, Langfuse free tier): **$0 marginal**.

| Cost component | Amount |
|---|---|
| LLM per qualified lead | ~$0.11 · `eval/e2e_test_results.json` + OpenRouter invoice |
| Infrastructure per lead | $0.00 (all free tiers) |
| **Total per qualified lead** | **~$0.11** |

This is well under Tenacious's $5 target. At production volume (60 outreach/week), batching further reduces per-lead LLM cost. Cost penalty threshold ($8/lead) is not at risk. Source: `eval/e2e_test_results.json`, OpenRouter dashboard ($12.75 total weekly spend).

---

## Speed-to-Lead Delta (Stalled-Thread Rate)

Current Tenacious manual process: **30–40% of qualified conversations stall in the first two weeks** because the initiating partner must personally handle replies while delivery work queues ahead (Tenacious CFO estimate).

In the 20-interaction e2e test, 8 prospect replies were received and handled within the same automated session — **0% stalled**. The agent has no human queue: replies trigger webhook → enrichment lookup → LLM or booking path within seconds. p50 reply-handling latency: 3,625 ms; p95: 14,392 ms (`eval/e2e_test_results.json`).

| | Stalled-thread rate |
|---|---|
| Tenacious manual (CFO estimate) | 30–40% |
| This system (e2e synthetic test) | 0% |
| **Delta** | **−30 to −40 pp** |

Note: the e2e test used synthetic prospect replies. Real-world stall rate will depend on reply volume vs. server uptime.

---

## Competitive-Gap Outbound Performance

Of 12 outreach events in the e2e test: **11 (92%) led with a research finding** (AI maturity score + signal-grounded ICP-specific language); **1 (8%) was a generic abstention pitch** (low-confidence no-match, `icp_confidence = LOW`, prospect: Meridian Co). All 12 had the honesty gate active (`constraints_applied: true`).

| Variant | Outreach count | Synthetic replies |
|---|---|---|
| Research-grounded | 11 (92%) | 8 / 11 (73%) |
| Generic abstention | 1 (8%) | 0 / 1 (0%) |

The 73% synthetic reply rate reflects scripted test respondents and does not represent real-world performance. Industry benchmarks: generic cold email 1–3%, signal-grounded top-quartile 7–12% (Clay/Smartlead case studies). Source: `eval/e2e_test_results.json`, variant field.

---

## Pilot Scope Recommendation

| Parameter | Value |
|---|---|
| Segment | Segment 1 — Recently funded Series A/B (clearest signal, highest ICP frequency in Crunchbase ODM) |
| Lead volume | 60 outreach / week × 4 weeks = 240 total |
| Weekly budget | $5 LLM + $0 infrastructure = $5/week ($20 pilot total) |
| Success criterion | Reply rate ≥ 5% at day 30 (above 1–3% generic baseline; below 7–12% top-quartile) |
| Kill condition | Reply rate < 3% after week 2, OR any probe F3 (bench over-commitment) incident confirmed by Tenacious delivery lead |

---

# Page 2 — The Skeptic's Appendix

## Four Failure Modes τ²-Bench Does Not Capture

**1. Offshore-perception objection.** τ²-Bench retail tests a customer-service agent handling exchanges; it never presents a CTO who replies "we tried offshore engineering before and it failed." The agent has no playbook for this objection and drifts to generic reassurances ("we're different because...") that read as scripted. To catch this: add adversarial reply scripts with offshore-skeptic personas to the probe library. Cost: ~4 hours of probe authoring + 1 held-out eval run.

**2. Time-delayed bench commitment mismatch.** τ²-Bench scores accuracy at a single moment. Tenacious's bench updates every Monday. If the agent commits "we have 5 ML engineers available" on Wednesday and the discovery call is the following Thursday, the bench may have changed. The benchmark doesn't model stale-commitment failures across time gaps. To catch this: inject bench-state diffs between outreach and discovery-call probe steps. Cost: bench-versioning infrastructure (~1 day).

**3. Multi-stakeholder thread contamination at the same company.** τ²-Bench is single-user per session. In Tenacious deployment, a VP Engineering and a co-founder at the same company can both receive cold outreach and reply independently. If the agent's in-memory state conflates the two threads, context from one leaks into the other (probe family F5-A in `failure_taxonomy.md`). τ²-Bench's dual-control pattern (agent + user simulator) doesn't test two simultaneous prospect threads per company. To catch this: parallel-session probe harness with shared company ID. Cost: ~2 days.

**4. Tone breakdown under dismissive reply.** τ²-Bench measures task completion (booking made, policy followed). It does not score whether the agent's tone remained non-condescending when a prospect replies "This is exactly the kind of AI pitch I delete every morning." Under this input, the agent risks either becoming defensive (Professional violation) or over-explaining the research methodology (Non-condescending violation). Neither shows up as a task failure in τ²-Bench; both show up as a brand event in deployment. To catch this: adversarial-reply tone-scoring probes graded by a separate judge LLM against the 5 style-guide markers. Cost: ~$0.50/eval run.

---

## Public-Signal Lossiness in AI-Maturity Scoring

**Quietly sophisticated but publicly silent.** A company running serious ML infrastructure entirely in-house: private GitHub, no public AI job posts (they've already hired), no executive AI commentary (intentional competitive silence). The agent's AI maturity score: 0 or 1. True maturity: 2–3. Agent behavior: sends Segment 1 generic scaling pitch or Segment 2 cost-restructuring pitch. Business impact: a technically sophisticated CTO receives a pitch that undersells the conversation — they forward it internally as an example of a vendor that "didn't do their homework." Estimated false-negative rate: ~15–20% of mature-but-silent companies in the Crunchbase ODM sample based on spot-check of 10 records.

**Loud but shallow.** A company with a CEO posting weekly about "our AI strategy," an "AI/ML Engineer" title on the team page (a rebranded data-analyst role), and a press release about "AI-powered features" (a vendor integration, not internal capability). Agent AI maturity score: 2 or 3. True maturity: 1. Agent behavior: sends Segment 4 capability-gap pitch or uses high-maturity Segment 1 language ("scale your AI team"). The prospect feels the agent misread them — they're not running a serious AI function and know it. Reply: silence or a polite "not a fit." Estimated false-positive rate: ~10–15% of self-promoting companies in the Crunchbase ODM sample.

---

## One Honest Unresolved Failure

**Probe D-01 — Bench over-commitment: NestJS stack committed through Q3 2026 (Family F3).**

The honesty gate (`agent/honesty_gate.py`) addresses F1 (confidence-unaware phrasing). It does not address F3. Probe D-01 injects a scenario where the prospect asks for a 3-engineer NestJS team; the bench summary (`seed/bench_summary.json`) shows NestJS engineers (2 available) are committed through Q3 2026. The agent currently has no live bench lookup at reply time — it reads bench context from the static system prompt set at initialization. Under D-01, the agent can confirm NestJS availability that does not exist.

**Business impact if deployed:** A prospect who asks specifically for NestJS capacity and receives a confident "yes" from the agent, then hears "actually those engineers are committed" from the Tenacious delivery lead on the discovery call, loses trust immediately. This is a harder brand event to recover from than a generic pitch — the prospect made a decision to engage *because of* a specific capacity claim. Fix requires a live bench-lookup gate before any capacity language is generated; estimated engineering cost: 1 day.

---

## Evidence

| Claim | Source |
|---|---|
| pass@1 = 0.2979, CI [0.2148, 0.3968] | `eval/score_log.json` (2026-04-24) |
| p50 = 3,625 ms, p95 = 14,392 ms | `eval/e2e_test_results.json` (2026-04-25) |
| ΔA = +20 pp | `eval/probe_results.json` (2026-04-25) |
| Cost per qualified lead ~$0.11 | OpenRouter invoice ($12.75 weekly) + `eval/e2e_test_results.json` |
| 11 research-grounded / 1 generic outreach | `eval/e2e_test_results.json`, variant field |
| Stalled-thread rate 30–40% (manual) | Tenacious CFO estimate, challenge brief |
| SOTA ~42% | τ²-bench leaderboard, Feb 2026 |
| 36 bench engineers | `seed/bench_summary.json`, 2026-04-21 |

*No ACV figures fabricated. `TENACIOUS_OUTBOUND_ENABLED` unset throughout; all outbound to `staff-sink@10academy.org`.*
