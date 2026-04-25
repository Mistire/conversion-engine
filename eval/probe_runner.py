"""
Act IV ablation — probe runner for F1 (confidence-unaware phrasing) probes.

Runs 5 representative F1 sub-type probes in two modes:
  baseline  — honesty_gate disabled (constraints = "")
  treatment — honesty_gate enabled  (constraints from build_constraints())

For each probe, the runner checks the composed email output against
specific forbidden / required strings — no LLM call needed, since
compose_outbound_email() is a deterministic template function.

Usage:
  cd conversion-engine
  python eval/probe_runner.py

Output: eval/probe_results.json + printed summary.
"""
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agent.models import (
    HiringSignalBrief, CompetitorGapBrief, ICPSegment, Confidence,
    AIMaturityScore, JobPostSignal, FundingEvent, LayoffEvent,
    LeadershipChange, CompetitorGapEntry,
)
from agent.email_handler import compose_outbound_email
from agent.honesty_gate import build_constraints


# ─── Probe definition ─────────────────────────────────────────────────────────

@dataclass
class Probe:
    id: str
    name: str
    brief: HiringSignalBrief
    gap_brief: CompetitorGapBrief | None
    # strings that must NOT appear in the email body (any → fail)
    forbidden: list[str] = field(default_factory=list)
    # strings that MUST appear in the email body (all → pass)
    required: list[str] = field(default_factory=list)
    # hard constraint: no partial credit
    hard: bool = True


@dataclass
class ProbeResult:
    probe_id: str
    probe_name: str
    mode: str   # "baseline" or "treatment"
    passed: bool
    email_subject: str
    email_body_excerpt: str
    constraint_block: str
    violations: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)


# ─── Build probes ─────────────────────────────────────────────────────────────

def _funded_brief(open_roles: int, ai_score: int, ai_confidence: Confidence,
                  has_layoff: bool = False) -> HiringSignalBrief:
    return HiringSignalBrief(
        company_name="AcmeCo",
        sector="fintech",
        employee_count=60,
        funding=FundingEvent(round_type="Series A", amount_usd=10_000_000, days_ago=60),
        layoff=LayoffEvent(date="2026-01-15", percentage_cut=20, days_ago=70) if has_layoff else None,
        job_posts=JobPostSignal(total_open_roles=open_roles, engineering_roles=open_roles, ai_adjacent_roles=0),
        ai_maturity=AIMaturityScore(score=ai_score, confidence=ai_confidence),
        icp_segment=ICPSegment.SEGMENT_1_FUNDED,
        icp_confidence=Confidence.HIGH,
    )


def _low_confidence_brief() -> HiringSignalBrief:
    return HiringSignalBrief(
        company_name="GammaCorp",
        sector="logistics",
        employee_count=40,
        job_posts=JobPostSignal(total_open_roles=2, engineering_roles=2),
        ai_maturity=AIMaturityScore(score=1, confidence=Confidence.LOW),
        icp_segment=ICPSegment.SEGMENT_1_FUNDED,
        icp_confidence=Confidence.LOW,
    )


def _stale_gap_brief() -> CompetitorGapBrief:
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    return CompetitorGapBrief(
        prospect_score=1,
        sector="fintech",
        top_quartile_threshold=2,
        prospect_percentile=0.25,
        gaps=["Three peers have dedicated MLOps-platform-engineer roles open for 60+ days."],
        confidence=Confidence.HIGH,
        generated_at=stale_ts,
    )


def _low_conf_gap_brief() -> CompetitorGapBrief:
    return CompetitorGapBrief(
        prospect_score=2,
        sector="fintech",
        top_quartile_threshold=3,
        prospect_percentile=0.40,
        gaps=["Some peers may have MLOps functions — signal is limited."],
        confidence=Confidence.LOW,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


PROBES: list[Probe] = [

    # F1-A: weak hiring velocity — fewer than 5 open roles
    Probe(
        id="F1-A",
        name="Weak velocity: no aggressive-hiring assertion (probe A-05)",
        brief=_funded_brief(open_roles=3, ai_score=2, ai_confidence=Confidence.HIGH),
        gap_brief=None,
        forbidden=["scaling aggressively", "hiring aggressively", "hiring fast", "rapid growth"],
        required=["open role"],  # must reference open roles as ask, not assertion
        hard=True,
    ),

    # F1-B: low AI maturity confidence — no AI assertion
    Probe(
        id="F1-B",
        name="Low AI confidence: no AI function assertion (probe A-06)",
        brief=_funded_brief(open_roles=6, ai_score=2, ai_confidence=Confidence.LOW),
        gap_brief=None,
        forbidden=["your AI team", "strong AI", "investing in AI", "your AI roadmap"],
        required=[],
        hard=True,
    ),

    # F1-C: layoff + funding — no growth language
    Probe(
        id="F1-C",
        name="Post-layoff: no growth language (probe C-01)",
        brief=_funded_brief(open_roles=5, ai_score=1, ai_confidence=Confidence.MEDIUM, has_layoff=True),
        gap_brief=None,
        forbidden=["scale your", "scaling your", "grow your", "expansion", "hiring momentum"],
        required=["restructur"],  # body should reference restructuring context
        hard=True,
    ),

    # F1-D: low-confidence gap brief — ask, not assert
    Probe(
        id="F1-D",
        name="Low-conf gap: question framing not assertion (probe C-03)",
        brief=_funded_brief(open_roles=7, ai_score=2, ai_confidence=Confidence.HIGH),
        gap_brief=_low_conf_gap_brief(),
        forbidden=["Three of your competitors have", "your competitors have built", "peers have"],
        required=[],
        hard=True,
    ),

    # F1-G: abstention — icp_confidence=LOW → generic email only
    Probe(
        id="F1-G",
        name="Abstention: generic email when confidence LOW (probe B-09)",
        brief=_low_confidence_brief(),
        gap_brief=None,
        forbidden=[
            "Series A", "funding round", "restructur",
            "AI team", "capability gap",
        ],
        required=["15-minute"],  # must still have a single ask (text uses "15-minute")
        hard=True,
    ),
]


# ─── Runner ───────────────────────────────────────────────────────────────────

def run_probe(probe: Probe, mode: str) -> ProbeResult:
    if mode == "treatment":
        constraints = build_constraints(probe.brief, probe.gap_brief)
    else:
        constraints = ""  # gate disabled

    email = compose_outbound_email(
        prospect_name="Elena Marsh",
        company_name=probe.brief.company_name,
        prospect_title="VP Engineering",
        brief=probe.brief,
        gap_brief=probe.gap_brief,
        honesty_constraints=constraints,
    )

    body = (email.text_body or "").lower()
    subject = email.subject or ""

    violations = [f for f in probe.forbidden if f.lower() in body]
    missing = [r for r in probe.required if r.lower() not in body]

    passed = len(violations) == 0 and len(missing) == 0

    return ProbeResult(
        probe_id=probe.id,
        probe_name=probe.name,
        mode=mode,
        passed=passed,
        email_subject=subject,
        email_body_excerpt=email.text_body[:300] if email.text_body else "",
        constraint_block=constraints[:200] if constraints else "(none)",
        violations=violations,
        missing_required=missing,
    )


def run_all() -> None:
    results: list[ProbeResult] = []

    for mode in ("baseline", "treatment"):
        for probe in PROBES:
            r = run_probe(probe, mode)
            results.append(r)

    # Summary
    baseline = [r for r in results if r.mode == "baseline"]
    treatment = [r for r in results if r.mode == "treatment"]

    b_pass = sum(1 for r in baseline if r.passed)
    t_pass = sum(1 for r in treatment if r.passed)
    n = len(PROBES)

    delta_a = (t_pass - b_pass) / n

    print("\n" + "=" * 60)
    print("Act IV Ablation — F1 Probe Results")
    print("=" * 60)
    print(f"{'Probe':<8} {'Name':<52} {'Baseline':<10} {'Treatment':<10}")
    print("-" * 80)
    for i, probe in enumerate(PROBES):
        b = baseline[i]
        t = treatment[i]
        b_str = "PASS" if b.passed else f"FAIL {b.violations or b.missing_required}"
        t_str = "PASS" if t.passed else f"FAIL {t.violations or t.missing_required}"
        print(f"{probe.id:<8} {probe.name[:50]:<52} {b_str:<10} {t_str:<10}")

    print("-" * 80)
    print(f"\nBaseline pass rate:  {b_pass}/{n} = {b_pass/n:.2%}")
    print(f"Treatment pass rate: {t_pass}/{n} = {t_pass/n:.2%}")
    print(f"ΔA = {delta_a:+.2%}  ({'+' if delta_a >= 0 else ''}{t_pass - b_pass} probes flipped)")

    # Write JSON
    out_path = ROOT / "eval" / "probe_results.json"
    summary = {
        "run_at": datetime.utcnow().isoformat(),
        "n_probes": n,
        "baseline_pass": b_pass,
        "baseline_pass_rate": round(b_pass / n, 4),
        "treatment_pass": t_pass,
        "treatment_pass_rate": round(t_pass / n, 4),
        "delta_a": round(delta_a, 4),
        "results": [asdict(r) for r in results],
    }
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nFull results → {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
