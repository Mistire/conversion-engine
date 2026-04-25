# Demo Script — Tenacious Conversion Engine (8 min target)

**Speaker:** Mistire Daniel  
**Date:** 2026-04-25  
**Recording target:** 7–9 minutes, screen + voice, full terminal visible  
**Prospect used:** Karl Fischer, Head of Data, Delphi Analytics (Segment 4 — capability gap)

---

## Before you hit record

```bash
cd /home/mistire/Projects/10Academy/course/week-10/conversion-engine
source .venv/bin/activate
python scripts/smoke_test.py        # confirm all 6 integrations green
```

Then open a second terminal pane with `memo.pdf` or have it ready in a PDF viewer.  
Set terminal font to 14–16pt, dark theme.

---

## Segment 1 — Intro (0:00–0:30)

**Show:**

```bash
ls
```

**Say:**
> "This is the Tenacious Conversion Engine — a fully automated B2B sales pipeline
> built for 10Academy TRP1 Week 10. I'll walk through the full prospect journey:
> signal enrichment, grounded cold outreach, a prospect reply, discovery call booking
> via Cal.com, and real-time HubSpot updates. The prospect is Karl Fischer,
> Head of Data at Delphi Analytics."

Briefly open `memo.pdf` so the 2-page summary is visible, then close it.

---

## Segment 2 — Run the demo (0:30–5:30)

**Say:**
> "The demo runner runs the full pipeline end-to-end with a single command."

**Show:**

```bash
python scripts/demo_runner.py
```

Let it run. Narrate each step as the output scrolls — cues below.

### Step [1] — Hiring Signal Brief

**Say while output scrolls:**
> "Step 1 is the hiring signal brief. Five signals are scored — Crunchbase funding,
> layoffs.fyi, job-post velocity, leadership changes, and the AI maturity score.
> Each signal shows its confidence level. Delphi has 7 open roles, 4 AI-adjacent —
> a ×2.1 velocity increase in 60 days — and an AI maturity score of 2 out of 3
> with HIGH confidence. ICP segment: specialized capability gap."

**Point at:** the per-signal breakdown lines and the GREEN HIGH confidence labels.

### Step [2] — Competitor Gap Brief

**Say:**
> "Step 2 generates the competitor gap brief. Top-quartile adtech peers score 3 out
> of 3 — Delphi is 1 point behind. Three competitors filled MLOps platform engineer
> roles in the last 60 days. Delphi has had 2 open for 75 days. That's the specific
> gap we reference in outreach."

**Point at:** the three gap lines.

### Step [3] — Honesty Gate

**Say:**
> "Step 3 is the honesty gate — purely deterministic, no LLM call, under a
> millisecond. It reads confidence flags from the brief and writes constraints
> the LLM must follow. Here it fires one: the tech stack was inferred from job posts,
> not confirmed, so the email must hedge rather than assert."

### Step [4] — Outreach Email

**Say:**
> "Step 4 composes the outreach email. Subject line: 'Question: AI/ML capability gap
> at Delphi Analytics.' The body references the specific gap finding — 4 AI-adjacent
> roles, the 1-point gap vs sector leaders — and ends with a 30-minute call ask.
> Variant is research_grounded because real signals drove every claim."

**Point at:** subject line and the signal sentences in the body.

### Step [5] — Send (Resend / staff sink)

**Say:**
> "Step 5 sends via Resend. LIVE_MODE is false, so all outbound routes to the staff
> sink — `staff-sink@10academy.org` — with the original recipient preserved in headers.
> No message reaches a real person until a Tenacious reviewer approves the draft.
> SMS is not sent here — email is the primary channel for cold outreach to founders,
> CTOs, and VPs Engineering."

### Step [6] — HubSpot

**Say:**
> "Step 6 upserts the HubSpot contact. Thirteen fields are written — ICP segment,
> confidence, AI maturity score, sector, enrichment timestamp, signal brief JSON,
> gap brief JSON, and email thread active. All non-null, timestamp is current."

**Point at:** the fields table and the enrichment_timestamp line.

If you want to show the live HubSpot record: open the URL from the output in a browser.

### Step [7] — Prospect Reply

**Say:**
> "Step 7 simulates the prospect reply. Karl writes back: 'Your MLOps gap research
> is spot on — we've had 2 platform engineer roles open for 3 months. Would Wednesday
> or Thursday work for a call?' The system detects booking intent immediately —
> no LLM call needed. SMS is now unlocked as a secondary channel for scheduling
> coordination, but wasn't needed in this conversation."

**Point at:** the green tick "Booking intent detected" line.

### Step [8] — Cal.com Booking

**Say:**
> "Step 8 fetches available Cal.com slots and creates the booking. Three slots are
> offered in the reply. The agent books the first one — a 30-minute discovery call.
> The booking UID is returned. Voice is the final channel: the call is booked by
> the agent and delivered by a human Tenacious delivery lead."

**Point at:** the booking UID and title lines.

### Step [9] — HubSpot Update

**Say:**
> "Step 9 writes the booking back to HubSpot —
> tenacious_discovery_call_booked is now true, booking UID is stored."

### Step [10] — Channel Hierarchy

**Say:**
> "Step 10 summarises the channel hierarchy: email is primary — cold outreach,
> research findings, follow-ups. SMS is secondary — warm leads only, scheduling
> coordination after email reply. Voice is the discovery call, booked by the agent
> and delivered by a human."

---

## Segment 3 — Integration health check (5:30–6:30)

**Say:**
> "All six integrations are live. Let me run the smoke test — this pings each one
> without spending LLM credits."

**Show:**

```bash
python scripts/smoke_test.py
```

Wait for green ticks on all six: Resend, Africa's Talking, HubSpot, Cal.com,
Langfuse, OpenRouter.

---

## Segment 4 — Wrap-up (6:30–7:30)

**Show:** open `memo.pdf`, navigate to the evidence table on the final page.

**Say:**
> "The full evidence is in memo.pdf. To summarise: signal-grounded cold outreach
> composed from five live data signals, honesty gate enforcing brand policy before
> every draft, HubSpot populated in real time, discovery call booked via Cal.com —
> all in a single pipeline run. Channel hierarchy throughout: email primary,
> SMS secondary for warm scheduling, voice for the booked discovery call.
> Thank you."

---

## Recording Checklist

- [ ] `python scripts/smoke_test.py` — all 6 green before starting
- [ ] Terminal font 14–16pt, dark theme, visible at 1080p
- [ ] `demo_runner.py` output fits in one scroll — don't zoom in so much it clips
- [ ] Have `memo.pdf` open in a second pane or window for segments 1 and 4
- [ ] Speak at a steady pace — the output takes ~20 seconds to finish; fill with narration

## Recording tools

```bash
# Kazam (lightweight)
sudo apt install kazam

# OBS Studio (full control)
sudo apt install obs-studio

# ffmpeg (no GUI)
ffmpeg -f x11grab -r 30 -s 1920x1080 -i :0.0 -f pulse -ac 2 -i default \
  -c:v libx264 -preset ultrafast -c:a aac demo_video.mp4
# Press q to stop
```
