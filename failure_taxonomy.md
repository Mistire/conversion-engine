# Failure Taxonomy — Tenacious Conversion Engine (Act III)

**Author:** Mistire Daniel | **Date:** 2026-04-25  
**Source probes:** `probes/probe_library.md` (40 probes across 6 categories)  
**Agent under test:** `agent/agent.py` with `qwen/qwen3-235b-a22b` backbone via OpenRouter

---

## Overview

This taxonomy organizes observed and anticipated failure modes into five root-cause families. Each family shares a single underlying cause that a targeted mechanism can address. The taxonomy drives the Act IV mechanism selection: the highest-frequency, highest-severity family becomes the target.

| Family | Root cause | Probe coverage | Severity |
|--------|-----------|----------------|----------|
| F1 — Confidence-unaware phrasing | Agent asserts claims without gating on signal confidence | A-05, A-06, B-09, C-01, C-02, C-03, C-04 | Critical |
| F2 — ICP classification errors | Wrong segment chosen or disqualifier missed | B-01 through B-10 | High |
| F3 — Bench over-commitment | Agent promises capacity not on bench | A-08, D-01 through D-05 | Critical |
| F4 — Tone drift | Style-guide marker violated in output | A-01 through A-04, A-07, A-09, A-10 | High |
| F5 — Thread / data integrity | Wrong data used for wrong prospect or channel | E-01 through E-03, F-01 through F-07 | Critical / Medium |

---

## Family F1 — Confidence-Unaware Phrasing

### Root cause

The agent composes outreach from the hiring signal brief without reading the `honesty_flags` field or `segment_confidence` score. When these signals indicate LOW confidence, the agent continues to assert rather than ask — violating the Grounded and Honest tone markers.

### Sub-types

| Sub-type | Description | Probes |
|----------|-------------|--------|
| F1-A — Velocity over-claim | "scaling aggressively" when `open_roles_today < 5` or `velocity_label: insufficient_signal` | A-05 |
| F1-B — AI maturity over-claim | Asserting active AI function when `ai_maturity.score = 0` or confidence = `"low"` | A-06 |
| F1-C — Growth language post-layoff | Using expansion language when `layoff_event.detected: true` | C-01 |
| F1-D — Low-confidence gap stated as fact | Competitor gap with `confidence: "low"` asserted as definitive | C-03 |
| F1-E — Inferred stack stated as confirmed | Stack from job-post inference asserted as confirmed when `tech_stack_inferred_not_confirmed` flag set | C-02 |
| F1-F — Stale brief used | Competitor gap or hiring brief > 7 days old used without regeneration | C-05 |
| F1-G — Abstention suppressed | Segment-specific pitch sent despite `segment_confidence < 0.6` | B-09 |

### Mechanism gap

The agent's `SYSTEM_PROMPT` in `agent/agent.py` contains grounded-honesty rules (lines 57–64), but these are static text — the agent must infer when to apply them from the brief content. There is no programmatic gate that reads `honesty_flags` and injects confidence-aware phrasing constraints before email composition.

When the prompt says "if AI maturity confidence is LOW, use softer language," the LLM must judge this from the brief JSON embedded in the conversation. Under production load with long contexts, the model drifts toward confident assertions, especially when the user prompt instructs it to "sound informed" or "be specific."

### Why this family matters most

- Frequency: 7 of 40 probes (17.5%) target this family directly; an additional 5 from F2 (ICP abstention) share the confidence-gating mechanism.
- Brand risk: A single over-claiming email screenshotted by a senior engineering leader (the style guide explicitly references this risk) outweighs weeks of reply-rate gains.
- Measurability: `honesty_flags` and `segment_confidence` are structured fields in the brief JSON — a programmatic gate has a clean input signal.

---

## Family F2 — ICP Classification Errors

### Root cause

The agent classifies prospects using the ICP segment rules in the system prompt rather than a deterministic classifier. Priority conflicts (layoff + funding, leadership + funding) and disqualifiers (anti-offshore stance, interim CTO, competitor client) require multi-signal reasoning that the LLM applies inconsistently.

### Sub-types

| Sub-type | Description | Probes |
|----------|-------------|--------|
| F2-A — Priority conflict: layoff overrides funding | Agent picks Segment 1 when Segment 2 should dominate | B-01 |
| F2-B — Priority conflict: leadership overrides funding | Agent picks Segment 1 when Segment 3 should dominate | B-02 |
| F2-C — Disqualifier missed: Seg 1 | Corporate-strategic-only investor, anti-offshore stance, competitor client | B-03, B-04, B-10 |
| F2-D — Disqualifier missed: Seg 2 | Layoff > 40%, bankruptcy/acquisition | B-05 |
| F2-E — Disqualifier missed: Seg 3 | Interim CTO appointment | B-06 |
| F2-F — Disqualifier missed: Seg 4 | AI maturity < 2, or capability not on bench | B-07, B-08 |
| F2-G — Abstention suppressed | Confidence < 0.6 but segment-specific pitch sent | B-09 |

### Mechanism gap

The enrichment pipeline in `agent/enrichment.py` produces a `primary_segment_match` field, but the classification logic is inside the LLM call, not a deterministic rule engine. The priority ordering ("layoff > leadership change > capability gap > funding > abstain") and disqualifier checks exist in the system prompt as natural language, not as code that executes before the LLM sees the brief.

### Impact

Wrong segment → wrong pitch language → lower reply rate, possible brand damage (e.g., growth pitch to a post-layoff CFO).

---

## Family F3 — Bench Over-Commitment

### Root cause

The agent does not programmatically check `bench_summary.json` before composing outreach. Capacity claims ("we have engineers available") are generated from static prompt context rather than a live bench lookup. The gap is most acute for specialized or committed stacks.

### Sub-types

| Sub-type | Description | Probes |
|----------|-------------|--------|
| F3-A — Stack committed | NestJS committed through Q3 2026; agent still pitches | D-01 |
| F3-B — Team size exceeds available count | ML (5 available), Go (3 available) pitched above ceiling | D-02, D-05 |
| F3-C — Stack not on bench | Rust, blockchain, or other unlisted stacks pitched as Segment 4 | D-04 |
| F3-D — Regulated-industry caveat omitted | 7-day deploy quoted without +7 regulated-industry caveat | D-03 |
| F3-E — General capacity over-claim | Agent confirms specific staffing without routing to human | A-08 |

### Mechanism gap

`agent.py` embeds bench context in the system prompt as static JSON at initialization. If the bench changes (weekly Monday update per `bench_summary.json`) or a stack is committed mid-week, the running agent does not reload the bench state. The bench-to-brief match field in the hiring signal brief schema flags gaps, but the LLM does not always honor the `bench_available: false` signal.

---

## Family F4 — Tone Drift

### Root cause

The five tone markers (Direct, Grounded, Honest, Professional, Non-condescending) are described in the system prompt as rules, but no post-generation scoring step verifies the draft before sending. The LLM drifts under adversarial prompts instructing it to be "enthusiastic," "friendly," "thorough," or "persuasive."

### Sub-types

| Sub-type | Description | Probes |
|----------|-------------|--------|
| F4-A — Direct violations | Forbidden phrases in subject or body | A-01, A-04 |
| F4-B — Direct: structural violations | Multiple asks, subject > 60 chars | A-02, A-03 |
| F4-C — Grounded violations | Velocity or AI maturity over-assertion | A-05, A-06 |
| F4-D — Honest violations | Fabricated peer-company claims, bench over-commitment | A-07, A-08 |
| F4-E — Professional violations | "Bench" in prospect-facing copy, clichés | A-09 |
| F4-F — Non-condescending violations | Gap framed as leadership failure | A-10 |
| F4-G — Cold outreach constraints | Emoji, > 120 words, client name disclosed | F-05, F-06, F-07 |

### Mechanism gap

The style guide's tone-preservation check is mentioned in `seed/style_guide.md` as a design direction: "Your agent's tone-preservation check should score every draft against the five markers above." This check is not yet implemented. The current agent sends the first LLM completion directly through Resend without a scoring step.

---

## Family F5 — Thread and Data Integrity

### Root cause

Three distinct sub-causes share the thread/data umbrella: (a) wrong brief used for wrong prospect (context contamination), (b) sequence-rule violations (4th touch, opt-out re-engagement), and (c) channel-routing violations (cold SMS, unsolicited booking link).

### Sub-types

| Sub-type | Description | Probes |
|----------|-------------|--------|
| F5-A — Cross-prospect contamination | Brief A used in outreach for Prospect B | E-01, E-02, E-03 |
| F5-B — Sequence rule violations | 4th touch in 30 days; > 3 emails before opt-out | F-01 |
| F5-C — Opt-out not honored | Re-engagement after STOP signal | F-03 |
| F5-D — Channel policy violations | SMS to cold prospect; booking link without email reply | F-04 |
| F5-E — Scheduling data errors | Booking without timezone confirmation | F-02 |

### Mechanism gap

HubSpot holds the opt-out flag, thread history, and touch count, but the agent does not query HubSpot before composing the next message — it relies on its own conversation state. When state is reconstructed from HubSpot on a new session (e.g., after a restart), the touch-count and opt-out checks can be missed.

---

## Severity and Frequency Matrix

| Family | Probe count | Hard-constraint probes | Estimated pre-mechanism fail rate | Brand risk |
|--------|------------|------------------------|----------------------------------|------------|
| F1 — Confidence-unaware phrasing | 7 | 3 (A-05, A-06, B-09) | High (~60–70%) | Critical |
| F2 — ICP classification errors | 10 | 5 (B-01, B-04, B-07, B-08, B-09) | Medium (~40–50%) | High |
| F3 — Bench over-commitment | 5 | 4 (D-01, D-02, D-04, D-05) | Medium (~30–40%) | Critical |
| F4 — Tone drift | 10 | 6 (A-01, A-03, A-04, A-07, A-08) | Medium (~35–45%) | High |
| F5 — Thread/data integrity | 8 | 5 (E-01, E-03, F-01, F-03, F-04) | Low (~20–30%) | Critical |

**Estimated pre-mechanism fail rates** are qualitative predictions based on LLM behavior under adversarial prompts; the actual baseline will be measured in Act IV by running the probe suite against the dev-slice agent before the mechanism is applied.

---

## Ranking for Act IV target

Criteria: (1) highest estimated fail rate pre-mechanism, (2) tractability of a single mechanism fix, (3) measurability via ablation on the held-out slice.

| Rank | Family | Rationale |
|------|--------|-----------|
| **1** | **F1 — Confidence-unaware phrasing** | Highest estimated pre-mechanism fail rate; single programmatic gate (honesty_flags check) fixes most sub-types; clean before/after ablation signal |
| 2 | F2 — ICP classification | High probe count but fix requires re-engineering the classifier; larger scope than one Act IV day allows |
| 3 | F4 — Tone drift | Partially overlaps with F1; tone-preservation post-generation scorer is a natural complement mechanism |
| 4 | F3 — Bench over-commitment | Critical severity but lower frequency (fewer edge-case triggers in the wild) |
| 5 | F5 — Thread/data integrity | Mostly infrastructure fixes (HubSpot query gates); not an LLM-output quality problem |

**Selected target for Act IV: Family F1 — Confidence-Unaware Phrasing.** See `target_failure_mode.md`.
