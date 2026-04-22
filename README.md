# Conversion Engine — Tenacious Consulting & Outsourcing

An automated lead generation and conversion system for Tenacious Consulting and Outsourcing. The system finds prospective B2B clients from public data, qualifies them against hiring signals and AI maturity, runs a research-grounded email nurture sequence, and books discovery calls.

**10Academy TRP1 — Week 10 Challenge**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Conversion Engine                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Public Data Sources        Signal Enrichment Pipeline          │
│  ──────────────────         ─────────────────────────           │
│  Crunchbase ODM  ──────────▶ Firmographics                      │
│  layoffs.fyi     ──────────▶ Layoff signal (Segment 2)          │
│  Job boards      ──────────▶ Job-post velocity                  │
│  Press/LinkedIn  ──────────▶ Leadership change (Segment 3)      │
│  GitHub/BuiltWith ─────────▶ AI maturity score (0–3)            │
│                             ▼                                   │
│                     hiring_signal_brief.json                    │
│                     competitor_gap_brief.json                   │
│                             │                                   │
│                             ▼                                   │
│                    ┌─────────────────┐                          │
│                    │  LLM Agent      │  (OpenRouter dev tier /  │
│                    │  Orchestrator   │   Claude eval tier)      │
│                    └────────┬────────┘                          │
│                             │  ICP segment classification       │
│                             │  Pitch personalization            │
│                             │  Grounded-honesty enforcement     │
│                             │                                   │
│          ┌──────────────────┼──────────────────┐               │
│          ▼                  ▼                  ▼               │
│    Email (PRIMARY)    SMS (SECONDARY)    Voice (BONUS)          │
│    Resend/MailerSend  Africa's Talking   Shared Voice Rig       │
│    Cold outreach      Warm scheduling    Discovery call          │
│          │                  │                  │               │
│          └──────────────────┴──────────────────┘               │
│                             │                                   │
│                    ┌────────▼────────┐                          │
│                    │   HubSpot CRM   │  (MCP server)            │
│                    │   Cal.com       │  (Self-hosted Docker)    │
│                    │   Langfuse      │  (Trace + cost)          │
│                    └─────────────────┘                          │
│                                                                 │
│  Evaluation: τ²-Bench retail domain  (ground-truth benchmark)  │
└─────────────────────────────────────────────────────────────────┘
```

### Channel Priority (Tenacious-specific)
1. **Email** — primary cold outreach (founders/CTOs/VPs live in email)
2. **SMS** — secondary, only for warm leads who replied by email and want fast scheduling coordination
3. **Voice** — final channel; booked discovery call delivered by a human Tenacious delivery lead

---

## Repository Structure

```
conversion-engine/
├── agent/                    # All agent source files
│   ├── config.py             # Settings (loaded from .env)
│   ├── enrichment.py         # Signal enrichment pipeline
│   ├── email_handler.py      # Resend/MailerSend integration + webhook
│   ├── sms_handler.py        # Africa's Talking integration
│   ├── hubspot_client.py     # HubSpot MCP integration
│   ├── calcom_client.py      # Cal.com booking flow
│   ├── agent.py              # Main LLM agent orchestrator
│   ├── models.py             # Pydantic data models
│   └── main.py               # FastAPI app (webhook endpoints)
├── eval/                     # τ²-Bench evaluation harness
│   ├── harness.py            # Wrapped τ²-Bench runner → Langfuse + score_log.json
│   ├── baseline_runner.py    # 5-trial pass@1 baseline script
│   ├── score_log.json        # Baseline results with 95% CI
│   └── trace_log.jsonl       # Full τ²-Bench trajectories
├── probes/                   # Adversarial probes (Act III — due Day 5)
│   ├── probe_library.md
│   ├── failure_taxonomy.md
│   └── target_failure_mode.md
├── data/
│   ├── crunchbase/           # Crunchbase ODM sample (1,001 records)
│   ├── layoffs/              # layoffs.fyi CSV
│   └── job_posts/            # Frozen job-post snapshot
├── baseline.md               # Act I results (max 400 words)
├── requirements.txt
├── .env.example              # Copy to .env and fill in credentials
├── docker-compose.yml        # Cal.com self-hosted setup
└── README.md
```

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/Mistire/conversion-engine.git
cd conversion-engine
```

### 2. Create the Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
playwright install chromium
```

### 4. Configure credentials

```bash
cp .env.example .env
# Edit .env and fill in your API keys (see comments in .env.example)
```

**Required accounts (all free, no credit card):**

| Service | Sign-up URL | What to get |
|---------|-------------|-------------|
| OpenRouter | https://openrouter.ai | API key → `OPENROUTER_API_KEY` |
| Langfuse | https://cloud.langfuse.com | Public + Secret key → `LANGFUSE_*` |
| Resend | https://resend.com | API key → `RESEND_API_KEY` |
| Africa's Talking | https://account.africastalking.com/apps/sandbox | API key + shortcode → `AFRICASTALKING_*` |
| HubSpot | https://developers.hubspot.com | Private app access token → `HUBSPOT_ACCESS_TOKEN` |

### 5. Set up Cal.com (self-hosted)

```bash
# Cal.com runs locally via Docker
docker compose up -d calcom
# Access at http://localhost:3000
# Create an event type and note the event_type_id → CALCOM_EVENT_TYPE_ID
```

### 6. Set up τ²-Bench

```bash
git clone https://github.com/sierra-research/tau2-bench.git
cd tau2-bench
pip install -r requirements.txt
```

### 7. Run the eval baseline

```bash
cd eval
python baseline_runner.py
# Writes score_log.json and trace_log.jsonl
```

### 8. Start the agent server

```bash
uvicorn agent.main:app --host 0.0.0.0 --port 8080 --reload
```

---

## Kill Switch

**CRITICAL:** By default `LIVE_MODE=false` in `.env`. In this mode, all outbound email and SMS is routed to the staff sink (`STAFF_SINK_EMAIL` / `STAFF_SINK_SMS`). No real Tenacious prospects are contacted.

Setting `LIVE_MODE=true` requires explicit written approval from program staff and the Tenacious executive team. Do not change this default.

---

## Data Handling

- No real Tenacious customer data is used. All prospects during the challenge week are synthetic.
- Seed materials (sales deck, case studies, pricing sheet) are not committed to this repo and must be deleted from personal infrastructure after the week ends.
- All system outputs that include Tenacious-branded content are marked `draft` in metadata.

---

## Budget Envelope

| Item | Target |
|------|--------|
| Africa's Talking sandbox | $0 |
| HubSpot Developer Sandbox | $0 |
| Cal.com self-hosted | $0 |
| LLM — dev tier (Days 1–4) | ≤ $4 |
| LLM — eval tier (Days 5–7) | ≤ $12 |
| Langfuse cloud | $0 |
| **Total** | **≤ $20** |

---

## Grading Observables

| Observable | What it measures |
|-----------|-----------------|
| Reproduction fidelity | τ²-Bench retail baseline within tolerance of pinned reference |
| Probe originality | Probes diagnostic of Tenacious-specific failure modes |
| Mechanism attribution | Delta A positive with 95% CI separation, p < 0.05 |
| Cost-quality Pareto | Cost per qualified lead < $5 (target), < $8 (hard cap) |
| Evidence-graph integrity | Every memo claim traces to a trace file or published source |
| Skeptic's appendix quality | Tenacious-specific risks (brand, bench mismatch, offshore perception) |
