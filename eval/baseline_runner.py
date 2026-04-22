"""
Act I baseline runner.

Usage:
  cd conversion-engine
  python eval/baseline_runner.py

Runs 5-trial pass@1 on the 30-task dev slice using the dev-tier model.
Writes score_log.json and trace_log.jsonl to eval/.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT))

from eval.harness import run_baseline, DEV_SLICE

DEV_MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen3-235b-a22b")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

# tau2-bench uses LiteLLM — prefix the model with openrouter/ for routing
LITELLM_MODEL = f"openrouter/{DEV_MODEL}" if OPENROUTER_KEY else "openai/gpt-4o-mini"


def main():
    print("=" * 60)
    print("Tenacious Conversion Engine — Act I Baseline")
    print("τ²-Bench retail domain, dev slice (30 tasks, 5 trials)")
    print("=" * 60)

    if not OPENROUTER_KEY:
        print("\nWARNING: OPENROUTER_API_KEY not set. Results will be mock/incomplete.")
        print("Set it in .env to run real evaluations.\n")

    # Set env vars for tau2-bench LiteLLM routing
    os.environ["OPENROUTER_API_KEY"] = OPENROUTER_KEY
    if OPENROUTER_KEY:
        os.environ["LITELLM_API_KEY"] = OPENROUTER_KEY

    print(f"\nModel: {LITELLM_MODEL}")
    print(f"Tasks: {len(DEV_SLICE)} (dev slice, tasks 0-29)")
    print("Trials: 5\n")

    entry = run_baseline(
        model=LITELLM_MODEL,
        domain="retail",
        num_trials=5,
        slice_name="dev",
        num_tasks=30,
        task_ids=DEV_SLICE,
    )

    print("\n" + "=" * 60)
    print("Baseline run complete. Results written to eval/score_log.json")
    print(f"pass@1 = {entry['pass_at_1_mean']:.3f} [{entry['pass_at_1_ci_lo']:.3f}, {entry['pass_at_1_ci_hi']:.3f}]")
    print("=" * 60)


if __name__ == "__main__":
    main()
