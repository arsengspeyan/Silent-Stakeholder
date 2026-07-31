"""
Orchestrator — runs all five pipeline stages in order and emits gaps.json.

Each stage is a separate script called via subprocess so they remain
fully independent and their caching/arg-parsing works correctly.

Usage:
    python src/pipeline.py               # use caches where available
    python src/pipeline.py --refresh     # recompute everything from scratch
    python src/pipeline.py --from label  # start from a specific stage
    make run                             # same as python src/pipeline.py
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Stages run in order. "refresh_ok" marks stages that accept --refresh.
STAGES = [
    {"name": "Ingest",   "script": "src/ingest.py",   "refresh_ok": True},
    {"name": "Cluster",  "script": "src/cluster.py",  "refresh_ok": True},
    {"name": "Label",    "script": "src/label.py",    "refresh_ok": True},
    {"name": "Match",    "script": "src/match.py",    "refresh_ok": True},
    {"name": "Score",    "script": "src/score.py",    "refresh_ok": False},
]


def run_stage(stage: dict, extra_args: list) -> float:
    args = [sys.executable, stage["script"]] + extra_args
    print(f"\n{'━' * 62}")
    print(f"  ▶  {stage['name'].upper()}")
    print(f"{'━' * 62}")

    t0     = time.time()
    result = subprocess.run(args, cwd=ROOT)
    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"\n  ✗  {stage['name']} failed (exit code {result.returncode})")
        sys.exit(result.returncode)

    print(f"\n  ✓  {stage['name']} done in {elapsed:.1f}s")
    return elapsed


def main():
    parser = argparse.ArgumentParser(
        description="Run the full Silent Stakeholder pipeline."
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Ignore all caches and recompute every stage from scratch.",
    )
    parser.add_argument(
        "--from", dest="from_stage", default=None, metavar="STAGE",
        help="Skip earlier stages and start from this one (e.g. --from label).",
    )
    args = parser.parse_args()

    # Decide which stages to run
    from_name = args.from_stage.lower() if args.from_stage else None
    skipping  = from_name is not None

    print(f"\n{'━' * 62}")
    print("  Silent Stakeholder — pipeline start")
    if args.refresh:
        print("  Mode: full refresh (all caches ignored)")
    if from_name:
        print(f"  Starting from: {args.from_stage}")
    print(f"{'━' * 62}")

    total_start = time.time()
    timings     = {}

    for stage in STAGES:
        name = stage["name"].lower()

        if skipping:
            if name == from_name:
                skipping = False   # start running from here
            else:
                print(f"  ↷  Skipping {stage['name']}")
                continue

        extra = ["--refresh"] if (args.refresh and stage["refresh_ok"]) else []
        timings[stage["name"]] = run_stage(stage, extra)

    total = time.time() - total_start

    print(f"\n{'━' * 62}")
    print(f"  Pipeline complete  ({total:.1f}s total)")
    print()
    for name, t in timings.items():
        print(f"    {name:<12}  {t:>5.1f}s")
    print()
    print(f"  Output: {ROOT / 'gaps.json'}")
    print(f"  Viewer: make viewer  →  http://localhost:8000/viewer/")
    print(f"{'━' * 62}\n")


if __name__ == "__main__":
    main()
