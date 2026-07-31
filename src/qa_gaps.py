"""
Quality tester — QA critic agent (Anthropic Claude)

After the pipeline produces ranked gaps, the QA critic agent asks Claude to judge
each gap against the hackathon bar:
  - Is the need statement a latent need, or just a complaint summary?
  - Do the sample reviews actually support the stated need?

Results are cached to data/qa_cache/<cluster_id>.json and aggregated in
data/gaps_qa.json. Re-runs are free when cached.

This is a testing / QA layer only — it never modifies gaps.json, scores, or ranks.

Usage:
    python src/qa_gaps.py              # test headline gaps (top 5)
    python src/qa_gaps.py --all        # test every ranked gap
    python src/qa_gaps.py --refresh    # ignore QA cache
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

# ── constants ─────────────────────────────────────────────────────────────────

MODEL        = "claude-sonnet-4-6"
MAX_SAMPLES  = 8   # reviews sent to the critic per gap

ROOT           = Path(__file__).parent.parent
DATA_DIR       = ROOT / "data"
GAPS_FILE      = ROOT / "gaps.json"
REVIEWS_FILE   = DATA_DIR / "reviews.json"
QA_CACHE_DIR   = DATA_DIR / "qa_cache"
QA_OUTPUT_FILE = DATA_DIR / "gaps_qa.json"

VALID_GRADES = {"pass", "warn", "fail"}


# ── helpers ───────────────────────────────────────────────────────────────────

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_response(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned.strip())
    return json.loads(cleaned)


def sample_reviews_for_gap(gap: dict, id_to_review: dict) -> list[dict]:
    """Prefer embedded samples; otherwise longest reviews from evidence IDs."""
    if gap.get("sample_reviews"):
        return gap["sample_reviews"][:MAX_SAMPLES]

    reviews = [
        id_to_review[rid]
        for rid in gap.get("evidence", {}).get("review_ids", [])
        if rid in id_to_review
    ]
    reviews.sort(key=lambda r: len(r.get("text") or ""), reverse=True)
    return reviews[:MAX_SAMPLES]


def cache_path(cluster_id: str) -> Path:
    # cluster_id may contain parentheses (merged groups)
    safe = cluster_id.replace("/", "_")
    return QA_CACHE_DIR / f"{safe}.json"


# ── prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a strict QA reviewer for a hackathon project that finds LATENT user needs.

A LATENT NEED is what users actually need — in plain language — even if no single
review stated it exactly. It connects different surface complaints to one underlying
expectation.

A COMPLAINT SUMMARY only restates what people said ("users complain about lag",
"slow games mentioned often"). That scores poorly.

You will receive one ranked gap: its need statement, theme, verdict, optional merge
context, matched GitHub issues, and sample reviews.

Return ONLY valid JSON with exactly these keys:
  "grade"                  — "pass" | "warn" | "fail"
  "is_latent_need"         — true if the need statement inferrs beyond surface wording
  "complaint_summary_risk" — "low" | "medium" | "high"
  "evidence_alignment"     — "good" | "partial" | "weak" (do reviews support the need?)
  "reason"                 — 2-3 sentences explaining the grade
  "surface_complaints"     — array of 2-4 short paraphrases of what users literally said
  "latent_need_check"      — one sentence: the hidden need users implied but did not write
  "pitch_tip"              — one sentence advice for presenting this gap to judges

Grading guide:
  pass — clear latent need; reviews show different surface complaints pointing to same root
  warn — mostly latent but theme/title sounds like a complaint list, or evidence is mixed
  fail — need is just a frequency summary, praise cluster, or not supported by reviews

Rules:
- No prose before or after the JSON
- No markdown, no code fences
- Raw JSON only\
"""


def build_user_prompt(gap: dict, samples: list[dict]) -> str:
    lines = [
        f"Rank: {gap.get('rank', '?')}",
        f"Cluster ID: {gap['cluster_id']}",
        f"Theme: {gap.get('theme', '')}",
        f"Need: {gap.get('need', '')}",
        f"Verdict: {gap.get('verdict', '')}",
        f"Confidence: {gap.get('confidence_pct', gap.get('confidence', ''))}",
        f"Review count: {gap.get('review_count', '?')}",
    ]

    if gap.get("merge_reason"):
        lines += ["", f"Merge reason: {gap['merge_reason']}"]

    issue_nums = gap.get("evidence", {}).get("matched_issue_numbers", [])
    if issue_nums:
        lines += ["", f"Matched GitHub issues: {', '.join('#' + str(n) for n in issue_nums[:8])}"]

    top = gap.get("top_issue")
    if top:
        lines += [f"Top issue: #{top.get('issue_number')} — {top.get('title', '')}"]

    lines += ["", "Sample reviews:"]
    for r in samples:
        stars = r.get("stars", "?")
        text = (r.get("text") or "").strip()
        lines.append(f"[{r.get('id', '?')} | {stars}★] {text[:500]}")

    return "\n".join(lines)


# ── LLM call ──────────────────────────────────────────────────────────────────

def qa_gap(client: anthropic.Anthropic, gap: dict, samples: list[dict]) -> Optional[dict]:
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(gap, samples)}],
        )
        raw = response.content[0].text
    except Exception as e:
        print(f"\n  API error for {gap['cluster_id']}: {e}")
        return None

    try:
        result = parse_response(raw)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"\n  JSON parse error for {gap['cluster_id']}: {e}")
        print(f"  Raw: {raw[:300]}")
        return None

    required = (
        "grade", "is_latent_need", "complaint_summary_risk", "evidence_alignment",
        "reason", "surface_complaints", "latent_need_check", "pitch_tip",
    )
    for field in required:
        if field not in result:
            print(f"\n  Missing '{field}' for {gap['cluster_id']}")
            return None

    grade = str(result["grade"]).lower()
    if grade not in VALID_GRADES:
        print(f"\n  Invalid grade '{result['grade']}' for {gap['cluster_id']}")
        return None

    result["grade"] = grade
    return result


# ── reporting ─────────────────────────────────────────────────────────────────

def print_report(results: list[dict]) -> None:
    print("\n── QA report ───────────────────────────────────────────────────────────")
    print(f"{'Rk':<3} {'Grade':<5} {'Risk':<6} {'Evid':<7}  Theme")
    print("─" * 78)
    for r in sorted(results, key=lambda x: x.get("rank", 99)):
        grade_icon = {"pass": "✓", "warn": "!", "fail": "✗"}.get(r["grade"], "?")
        print(
            f"{r.get('rank', '?'):<3} "
            f"{grade_icon} {r['grade']:<3} "
            f"{r['complaint_summary_risk']:<6} "
            f"{r['evidence_alignment']:<7}  "
            f"{r.get('theme', '')[:42]}"
        )
    print("─" * 78)

    counts = {g: sum(1 for r in results if r["grade"] == g) for g in VALID_GRADES}
    print(f"  pass: {counts['pass']}  warn: {counts['warn']}  fail: {counts['fail']}")

    warns_fails = [r for r in results if r["grade"] != "pass"]
    if warns_fails:
        print("\n── Notes (warn / fail) ─────────────────────────────────────────────────")
        for r in sorted(warns_fails, key=lambda x: x.get("rank", 99)):
            print(f"\n  #{r.get('rank')} {r.get('theme', '')} [{r['grade'].upper()}]")
            print(f"  {r['reason']}")
            if r.get("pitch_tip"):
                print(f"  Tip: {r['pitch_tip']}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI quality tester for gaps.json (latent need vs complaint summary)."
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Test all ranked gaps, not just headline gaps.",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Re-run QA even if cached.",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)

    if not GAPS_FILE.exists():
        print(f"ERROR: {GAPS_FILE} not found. Run 'make run' first.", file=sys.stderr)
        sys.exit(1)

    gaps_data = load_json(GAPS_FILE)
    if args.all:
        gaps = gaps_data.get("all_gaps", [])
        label = "all ranked gaps"
    else:
        gaps = gaps_data.get("headline_gaps", [])
        label = "headline gaps"

    if not gaps:
        print("ERROR: no gaps to test.", file=sys.stderr)
        sys.exit(1)

    id_to_review = {}
    if REVIEWS_FILE.exists():
        id_to_review = {r["id"]: r for r in load_json(REVIEWS_FILE)}

    print(f"QA testing {len(gaps)} {label} from {GAPS_FILE.name}")
    QA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    hits = 0
    failed = 0

    for gap in gaps:
        cid = gap["cluster_id"]
        cfile = cache_path(cid)

        if not args.refresh and cfile.exists():
            qa = load_json(cfile)
            hits += 1
        else:
            samples = sample_reviews_for_gap(gap, id_to_review)
            rank = gap.get("rank", "?")
            print(f"  #{rank} {cid[:40]:<40} samples={len(samples)} … ", end="", flush=True)

            qa = qa_gap(client, gap, samples)
            if qa is None:
                failed += 1
                continue

            save_json(cfile, qa)
            print(qa["grade"])
            time.sleep(0.5)

        entry = {
            "cluster_id": cid,
            "rank": gap.get("rank"),
            "theme": gap.get("theme"),
            "need": gap.get("need"),
            "verdict": gap.get("verdict"),
            "confidence_pct": gap.get("confidence_pct"),
            **qa,
        }
        results.append(entry)

    output = {
        "meta": {
            "tested_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "scope": "all_gaps" if args.all else "headline_gaps",
            "gaps_tested": len(results),
        },
        "summary": {
            grade: sum(1 for r in results if r["grade"] == grade)
            for grade in sorted(VALID_GRADES)
        },
        "results": sorted(results, key=lambda r: r.get("rank") or 99),
    }
    save_json(QA_OUTPUT_FILE, output)

    print(f"\nSaved QA report → {QA_OUTPUT_FILE}")
    if hits:
        print(f"  Cache hits: {hits}")
    if failed:
        print(f"  WARNING: {failed} gap(s) failed QA")

    print_report(results)

    if any(r["grade"] == "fail" for r in results):
        sys.exit(2)


if __name__ == "__main__":
    main()
