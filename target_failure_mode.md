# Target Failure Mode — Act IV Mechanism Design

**Author:** Mistire Daniel | **Date:** 2026-04-25  
**Selected from:** `failure_taxonomy.md`, Family F1  
**Mechanism implementation:** `agent/honesty_gate.py`  
**Ablation slice:** held-out tasks 30–49 (20 tasks)

---

## 1. Target: Confidence-Unaware Phrasing (Family F1)

### What fails

The agent asserts claims about a prospect's state — hiring velocity, AI maturity, growth trajectory — without checking whether the underlying signals support assertive language. The `hiring_signal_brief.json` schema provides structured confidence signals (`honesty_flags`, `segment_confidence`, `ai_maturity.confidence`, `hiring_velocity.signal_confidence`), but the current agent embeds these fields in its context as raw JSON and relies on the LLM to self-regulate. Under adversarial prompts or long contexts, the LLM defaults to confident, assertive output.

### Evidence from the probe library

Seven probes directly test this failure mode (A-05, A-06, B-09, C-01, C-02, C-03, C-05). Three are hard-constraint probes (no partial credit). The failure is rooted in the same gap: structured confidence signals exist in the brief but are not programmatically enforced before the LLM generates the outreach draft.

### Why this is the highest-ROI target

1. **Single mechanism, multiple probe fixes.** A `honesty_gate()` function that reads four fields (`honesty_flags`, `segment_confidence`, `ai_maturity.confidence`, `hiring_velocity.signal_confidence`) and injects phrasing constraints into the system prompt should raise the pass rate on all 7 F1 probes and the B-09 abstention probe simultaneously.

2. **Measurable via ablation.** The before/after comparison is clean: run the probe suite against the agent with `honesty_gate` disabled (baseline), then with it enabled (treatment). ΔA = (treated pass rate) − (baseline pass rate) is directly attributable to the gate.

3. **Grounded in schema intent.** The `honesty_flags` field in `hiring_signal_brief.schema.json` exists specifically for this purpose: "Explicit flags the agent must respect when composing outreach." The gate is the missing enforcement layer.

4. **Style guide precedent.** `seed/style_guide.md` (section: Grounded) documents the ask-vs-assert rule with explicit examples. The mechanism codifies an existing intent.

---

## 2. Mechanism Design — `honesty_gate()`

### Location

New file: `agent/honesty_gate.py`. Called in `agent/agent.py` inside `initiate_outreach()` and `handle_email_reply()` before the LLM composition call.

### Inputs

```python
def honesty_gate(brief: HiringSignalBrief, gap_brief: CompetitorGapBrief | None) -> str:
    """
    Returns a phrasing-constraint block to prepend to the LLM system prompt.
    Empty string if no constraints needed (all signals high-confidence).
    """
```

### Logic

```
IF honesty_flags contains "weak_hiring_velocity_signal"
  → inject: "Do NOT assert aggressive hiring. Write: ask whether hiring velocity matches the runway."

IF honesty_flags contains "weak_ai_maturity_signal"
  → inject: "Do NOT assert an active AI function. Write: 'from what I can see publicly, ...' or omit AI language."

IF honesty_flags contains "layoff_overrides_funding"
  → inject: "Do NOT use growth or scaling language. Write: cost-discipline and delivery-maintenance language only."

IF honesty_flags contains "conflicting_segment_signals"
  → inject: "Do NOT use segment-specific pitch language. Write: a generic exploratory email."

IF honesty_flags contains "tech_stack_inferred_not_confirmed"
  → inject: "Do NOT assert the tech stack as confirmed. Write: 'we noticed X in your job posts — if that's your primary stack…'"

IF segment_confidence < 0.6
  → inject: "ABSTAIN from segment-specific pitch. Write: a generic exploratory email only. Do not name a segment."

IF ai_maturity.confidence == "low" AND ai_maturity.score >= 2
  → inject: "Use ask-mode for AI maturity: 'it looks like you may be building out an AI function — is that right?' Not 'you have a strong AI team.'"

IF gap_brief is not None AND gap_brief.gap_quality_self_check.at_least_one_gap_high_confidence == False
  → inject: "Do NOT assert competitor gap findings as facts. Write: 'we've seen some signal of this pattern — curious whether it applies to you.'"

IF gap_brief is not None AND gap_brief.generated_at is older than 7 days
  → inject: "The competitor gap brief is stale (> 7 days). Do NOT reference specific competitor findings. Use generic sector framing only."
```

### Output format

The gate returns a multi-line string prepended to the `SYSTEM_PROMPT` under a `### HONESTY CONSTRAINTS FOR THIS DRAFT` header. The LLM sees these constraints before any brief content.

### What it does NOT do

- Does not block the outreach entirely (that is the abstention path, which the gate triggers via the `segment_confidence < 0.6` rule).
- Does not rewrite the LLM's output post-generation (a post-generation scorer is a separate mechanism — see F4 tone drift in `failure_taxonomy.md`).
- Does not change the ICP segment classification (that is a separate F2 fix).

---

## 3. Expected ΔA

### Baseline (pre-mechanism)

Run the 40 probes against the dev-slice agent (`agent/agent.py` without `honesty_gate`). Expected fail rate on F1 probes: ~60–70% (7 probes × 0.65 = ~4.5 failures).

### Treatment (post-mechanism)

Run same probes with `honesty_gate` active. Expected fail rate on F1 probes: ~10–15% (residual LLM non-compliance on soft constraints).

### Predicted ΔA

- F1 probes: +50 pp improvement (~4.5 → ~0.7 failures out of 7)
- Full probe suite: +12–15 pp overall (7 F1 probes out of 40 total)

### Held-out ablation plan

1. Select 5 probes from the held-out slice that map to F1 sub-types (velocity claim, AI maturity claim, abstention trigger, layoff/growth conflict, low-confidence gap).
2. Run without gate → record pass count (baseline_ho).
3. Run with gate → record pass count (treated_ho).
4. Compute ΔA_ho = (treated_ho - baseline_ho) / 5.
5. Report p-value from one-sided binomial test (H0: ΔA ≤ 0, H1: ΔA > 0).

Minimum threshold for Act IV success: ΔA_ho ≥ 0.20 (at least 1 additional probe passing on the held-out slice).

---

## 4. Risk and Limitations

| Risk | Mitigation |
|------|------------|
| Over-suppression: gate fires on high-confidence signals because a minor flag is present | Gate checks flag-specific conditions, not flag count. A `tech_stack_inferred_not_confirmed` flag does not trigger the abstention path. |
| LLM ignores injected constraints | Constraints are prepended as a named block (`### HONESTY CONSTRAINTS`) to maximize attention. If compliance remains low, a post-generation scorer (F4 mechanism) is the fallback. |
| Gate increases latency | The gate is pure Python (dict lookups, string concatenation) — adds < 1ms per call. No additional LLM call required. |
| Gate does not help F2/F3/F4/F5 probes | Acknowledged. The gate is scoped to F1. Complementary mechanisms for the other families are documented in `failure_taxonomy.md` as future work. |

---

## 5. Files Changed by Act IV

| File | Change |
|------|--------|
| `agent/honesty_gate.py` | New file — gate function + unit tests |
| `agent/agent.py` | Import and call `honesty_gate()` before LLM composition in `initiate_outreach()` and `handle_email_reply()` |
| `eval/score_log.json` | New entry with held-out ablation results |
| `method.md` | Design rationale, scoring rubric, ΔA evidence graph |
