# Demo Script — Tenacious Conversion Engine (8 min target)

**Speaker:** Mistire Daniel  
**Date:** 2026-04-25  
**Recording target:** 7–9 minutes, screen + voice, full terminal + PDF viewer visible

---

## Segment 1 — Intro (0:00–0:45)

**Say:**
> "This is the Tenacious Conversion Engine, a fully automated B2B lead-generation and conversion system built in one week for 10Academy TRP1 Week 10. I'll walk through all five acts: the τ²-Bench baseline, the production stack, the failure taxonomy, the honesty gate mechanism, and the ablation results."

**Show:** `ls` at repo root, then open `memo.pdf` briefly so the 2-page summary is visible.

```bash
ls
```

---

## Segment 2 — Act I: τ²-Bench Baseline (0:45–2:00)

**Say:**
> "Act I is the benchmark baseline. We ran Qwen3-235B on the τ²-Bench retail domain dev slice — 30 tasks, 5 trials each, 150 task-trials total. 56 timed out; the harness patch in eval/harness.py guards against None simulation entries. The resulting pass-at-1 is 0.2979, with a 95% CI of 0.21 to 0.40, against a SOTA reference of around 42%. The gap is 12 points, explained mainly by incomplete coverage."

**Show** (type each):
```bash
cat eval/score_log.json | python3 -c "import json,sys; d=json.load(sys.stdin); e=d['entries'][-1]; print(f\"pass@1: {e['pass_at_1']:.4f}  CI: {e['ci_95']}  n_trials: {e['total_task_trials']}\")"
```

Then scroll `baseline.md`:
```bash
cat baseline.md
```

---

## Segment 3 — Act II: Production Stack (2:00–3:30)

**Say:**
> "Act II is the production stack. All six integrations are live: Resend for email, Africa's Talking for SMS on shortcode 73577, HubSpot CRM, Cal.com for booking, Langfuse for observability, and OpenRouter for LLM calls. Everything is in LIVE_MODE=false so all outbound routes to the staff sink. Let me run the smoke test."

**Show:**
```bash
python3 scripts/smoke_test.py
```

Wait for output, then:

**Say:**
> "All six integrations reported healthy. Now the 20-interaction end-to-end test — this covers 4 ICP segments, outreach and reply flows."

**Show:**
```bash
python3 scripts/test_e2e.py
```

Wait (~30–60 sec), then:
```bash
python3 -c "
import json
d = json.load(open('eval/e2e_test_results.json'))
print(f\"p50: {d['p50_latency_ms']} ms  p95: {d['p95_latency_ms']} ms\")
print(f\"Outreach routed to sink: {d['outreach_routed_to_sink']}/{d['total_outreach']}\")
print(f\"Gate fired: {d['honesty_gate_fired']}/{d['total_outreach']}\")
"
```

---

## Segment 4 — Act III: Failure Taxonomy (3:30–4:30)

**Say:**
> "Act III is the failure taxonomy and probe library. I defined 40 probes across 6 categories, 17 of which are hard-constraint. The five failure families are: F1 confidence-unaware phrasing at 60 to 70 percent estimated pre-mechanism fail rate, F2 ICP classification errors, F3 bench over-commitment, F4 tone drift, and F5 thread integrity. F1 was selected for Act IV — highest fail rate, cleanest structured signal."

**Show:**
```bash
head -80 failure_taxonomy.md
```

Then:
```bash
head -60 probes/probe_library.md
```

---

## Segment 5 — Act IV: Honesty Gate (4:30–6:30)

**Say:**
> "Act IV is the mechanism: the honesty gate. The file is agent/honesty_gate.py. build_constraints reads 8 conditions from the hiring signal brief — weak velocity, low AI confidence, recent layoff, stale gap brief, and others — and returns a named constraint block that's prepended to the LLM system prompt. Zero extra LLM calls, less than a millisecond of added latency."

**Show:**
```bash
cat agent/honesty_gate.py
```

Scroll slowly. Then:

**Say:**
> "The gate is wired into the agent at two points: initiate_outreach for the template path, and handle_email_reply for the LLM path. Let me show the key change in email_handler — the layoff guard."

**Show:**
```bash
grep -n "layoff" agent/email_handler.py
```

---

## Segment 6 — Ablation Results (6:30–7:45)

**Say:**
> "The ablation runs five F1 sub-type probes against compose_outbound_email — deterministic checks, no LLM calls. Baseline is 4 out of 5, or 80%. Treatment is 5 out of 5, or 100%. Delta A is plus 20 percentage points. The one flip is F1-C: when a company has both a funding event and a recent layoff, the original template used growth language — the gate detects the layoff flag and forces cost-and-delivery framing instead. Let me run it now."

**Show:**
```bash
python3 eval/probe_runner.py
```

Wait for output. Point at the table showing F1-C flipping from FAIL to PASS.

---

## Segment 7 — Wrap-up (7:45–8:00)

**Say:**
> "To summarize: τ²-Bench pass-at-1 of 29.79%, all six integrations live with p50 of 3.6 seconds end-to-end, a 40-probe failure taxonomy, and the honesty gate delivering a 20-point improvement in the F1 family. Full evidence is in memo.pdf. Thank you."

**Show:** Return to `memo.pdf` final page for the evidence table as you close.

---

## Recording Checklist

- [ ] Terminal font: 14–16pt, dark theme, visible at 1080p
- [ ] Run `python3 scripts/smoke_test.py` before starting — confirm all green
- [ ] Keep voice paced — 8 minutes is tight, avoid re-running commands that fail
- [ ] Commands above are copy-paste ready from this script

## Suggested recording tools (install one):

```bash
# OBS Studio (full-featured)
sudo apt install obs-studio

# Kazam (lightweight)
sudo apt install kazam

# SimpleScreenRecorder
sudo apt install simplescreenrecorder

# ffmpeg screen capture (no GUI needed)
ffmpeg -f x11grab -r 30 -s 1920x1080 -i :0.0 -f pulse -ac 2 -i default \
  -c:v libx264 -preset ultrafast -c:a aac demo_video.mp4
# Press q to stop recording
```
