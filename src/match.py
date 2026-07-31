"""
Stage 4 — Match

For each labeled cluster (named need), find the most similar GitHub issues
and assign a verdict: IGNORED | UNDER-PRIORITIZED | MISUNDERSTOOD | addressed.

Matching uses cosine similarity between need embeddings and issue embeddings —
NOT the LLM reading 4,004 issues. The LLM is only used for the ambiguous case:
when similarity is strong AND issues are actively open in the roadmap.

Milestone awareness (added for correctness):
  - Issues in OPEN milestones (Future, v1.21, v1.22 …) are actively planned.
  - Issues in CLOSED milestones were shipped. If users still complain about the
    same need after a shipped fix, the team addressed the wrong angle → MISUNDERSTOOD.
  - Issues with no milestone are acknowledged but unscheduled → UNDER-PRIORITIZED.

All LLM calls are cached to data/match_cache/<cluster_id>.json.

Usage:
    python src/match.py            # uses cached embeddings and LLM responses
    python src/match.py --refresh  # recomputes everything from scratch
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
import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ── tunable parameters ────────────────────────────────────────────────────────

TOP_K = 5

SIMILARITY_THRESHOLD = 0.35   # below this → IGNORED
STALE_DAYS           = 730    # ~2 years — issues not updated beyond this are stale

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
LLM_MODEL       = "claude-sonnet-4-6"

# Truncate issue body before embedding — keeps title signal dominant
MAX_BODY_CHARS = 400

# ── paths ─────────────────────────────────────────────────────────────────────

DATA_DIR         = Path(__file__).parent.parent / "data"
LABELED_CLUSTERS = DATA_DIR / "labeled_clusters.json"
ISSUES_FILE      = DATA_DIR / "issues.json"
MILESTONES_FILE  = DATA_DIR / "milestones.json"
ISSUE_EMBEDDINGS = DATA_DIR / "issue_embeddings.npy"
MATCH_CACHE_DIR  = DATA_DIR / "match_cache"
OUTPUT_FILE      = DATA_DIR / "matched_needs.json"

TODAY = datetime.now(timezone.utc)


# ── data helpers ──────────────────────────────────────────────────────────────

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def open_milestone_titles(milestones: list) -> set:
    """Return the set of milestone titles that are still open (not shipped)."""
    return {m["title"] for m in milestones if m["state"] == "open"}


# ── issue embedding ───────────────────────────────────────────────────────────

def issue_text(issue: dict) -> str:
    body = (issue.get("body") or "")[:MAX_BODY_CHARS]
    return f"{issue['title']} {body}".strip()


def embed_issues(issues: list, model: SentenceTransformer, refresh: bool) -> np.ndarray:
    if not refresh and ISSUE_EMBEDDINGS.exists():
        print(f"Cache hit: loading issue embeddings from {ISSUE_EMBEDDINGS}")
        embs = np.load(ISSUE_EMBEDDINGS)
        print(f"  shape={embs.shape}")
        return embs

    print(f"Embedding {len(issues):,} issues with '{EMBEDDING_MODEL}'…")
    texts = [issue_text(i) for i in issues]
    embs  = model.encode(texts, show_progress_bar=True, batch_size=64)
    np.save(ISSUE_EMBEDDINGS, embs)
    print(f"  Saved → {ISSUE_EMBEDDINGS}  shape={embs.shape}")
    return embs


# ── staleness + activity ──────────────────────────────────────────────────────

def days_since_update(issue: dict) -> int:
    updated = issue.get("updated_at") or ""
    if not updated:
        return 99999
    try:
        dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        return (TODAY - dt).days
    except ValueError:
        return 99999


def is_stale(issue: dict) -> bool:
    return days_since_update(issue) > STALE_DAYS


def in_open_milestone(issue: dict, open_ms: set) -> bool:
    """Issue is scheduled in a milestone that hasn't shipped yet."""
    ms = issue.get("milestone")
    return bool(ms and ms in open_ms)


def in_closed_milestone(issue: dict, open_ms: set) -> bool:
    """
    Issue's milestone has been shipped (closed).
    If users still report the same need after a shipped fix, the team
    addressed the wrong angle — a strong indicator of MISUNDERSTOOD.
    """
    ms = issue.get("milestone")
    return bool(ms and ms not in open_ms)


def is_active(issue: dict, open_ms: set) -> bool:
    """
    An issue is 'active' if it is open, not stale, not stuck in triage,
    and either has an open milestone or is unscheduled but recent.
    Issues in closed milestones are NOT active — their fix was shipped.
    """
    if issue["state"] != "open":
        return False
    if is_stale(issue):
        return False
    # Open milestone = actively planned
    ms = issue.get("milestone")
    if ms and ms not in open_ms:
        return False   # milestone is closed — fix was already shipped
    triage_labels = {"needs: triage", "needs triage", "triage"}
    issue_labels  = {lbl.lower() for lbl in issue.get("labels", [])}
    if triage_labels & issue_labels and not ms:
        return False
    return True


# ── LLM verdict (ambiguous case only) ────────────────────────────────────────

MATCH_SYSTEM = """\
You are a product analyst deciding whether GitHub roadmap issues address a specific
user need extracted from app reviews.

Return ONLY raw JSON with exactly two keys:
  "verdict"   — either "MISUNDERSTOOD" or "addressed"
  "rationale" — one sentence explaining the verdict

MISUNDERSTOOD: the roadmap issues touch a related topic but from a different angle,
or solve a narrower/different problem than what users actually need.
addressed: the roadmap directly works on the same need users expressed.

No prose before or after. No markdown. No code fences. Raw JSON only.\
"""


def llm_ambiguous_verdict(client: anthropic.Anthropic,
                          need: dict,
                          active_issues: list,
                          open_ms: set) -> Optional[dict]:
    issue_lines = []
    for iss in active_issues:
        ms     = iss.get("milestone") or "none"
        ms_st  = "open" if ms in open_ms else ("shipped" if ms != "none" else "none")
        labels = ", ".join(iss.get("labels", [])) or "none"
        body   = (iss.get("body") or "")[:200]
        issue_lines.append(
            f"  #{iss['id']}  [{iss['state']}]  milestone={ms} ({ms_st})  labels={labels}\n"
            f"  Title: {iss['title']}\n"
            f"  Body:  {body}"
        )

    prompt = (
        f"User need (from {need['size']} app reviews):\n"
        f"  Theme: {need['theme']}\n"
        f"  Need : {need['need']}\n\n"
        f"Matching GitHub issues:\n"
        + "\n\n".join(issue_lines)
    )

    try:
        resp = client.messages.create(
            model=LLM_MODEL,
            max_tokens=150,
            system=MATCH_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
    except Exception as e:
        print(f"\n  API error: {e}")
        return None

    try:
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned.strip())
        result  = json.loads(cleaned)
        if "verdict" not in result or "rationale" not in result:
            raise ValueError("missing fields")
        return result
    except Exception as e:
        print(f"\n  Parse error ({e}) | raw: {raw[:200]}")
        return None


# ── core matching logic ───────────────────────────────────────────────────────

def match_need(need: dict, issues: list,
               need_emb: np.ndarray, issue_embs: np.ndarray,
               open_ms: set,
               client: anthropic.Anthropic, refresh: bool) -> dict:

    sims    = cosine_similarity(need_emb.reshape(1, -1), issue_embs)[0]
    top_idx = sims.argsort()[::-1][:TOP_K]

    top_matches = []
    for idx in top_idx:
        iss = issues[idx]
        top_matches.append({
            "issue_number":     iss["id"],
            "title":            iss["title"],
            "similarity":       float(sims[idx]),
            "state":            iss["state"],
            "labels":           iss.get("labels", []),
            "milestone":        iss.get("milestone"),
            "updated_at":       iss.get("updated_at"),
            "_stale":           is_stale(iss),
            "_active":          is_active(iss, open_ms),
            "_closed_milestone": in_closed_milestone(iss, open_ms),
        })

    best_sim = top_matches[0]["similarity"] if top_matches else 0.0

    # ── verdict rules ─────────────────────────────────────────────────────────

    if best_sim < SIMILARITY_THRESHOLD:
        # Rule 1: Nothing close in the roadmap → IGNORED
        verdict   = "IGNORED"
        rationale = (f"Best match similarity {best_sim:.3f} < threshold "
                     f"{SIMILARITY_THRESHOLD} — roadmap has no issue covering this need.")

    elif any(m["_closed_milestone"] for m in top_matches):
        # Rule 2: A related fix was SHIPPED (closed milestone) but users still complain.
        # The team addressed the issue but missed the real scope → MISUNDERSTOOD.
        shipped = next(m for m in top_matches if m["_closed_milestone"])
        verdict   = "MISUNDERSTOOD"
        rationale = (
            f"Issue #{shipped['issue_number']} ('{shipped['title'][:50]}') was "
            f"closed in milestone '{shipped['milestone']}' (shipped), but users "
            f"still report this need — team fixed a narrower case than what users "
            f"actually experience."
        )

    elif not any(m["_active"] for m in top_matches):
        # Rule 3: Related issues exist but none are actively being worked on
        closed_n = sum(1 for m in top_matches if m["state"] == "closed")
        stale_n  = sum(1 for m in top_matches if m["_stale"])
        verdict   = "UNDER-PRIORITIZED"
        rationale = (f"Found {len(top_matches)} related issues (best sim {best_sim:.3f}): "
                     f"{closed_n} closed, {stale_n} stale, none in active milestone — "
                     f"need is acknowledged but not being worked on.")

    else:
        # Rule 4: Active issues exist — use LLM to judge MISUNDERSTOOD vs. addressed
        cid        = need["cluster_id"]
        cache_file = MATCH_CACHE_DIR / f"{cid}.json"

        if not refresh and cache_file.exists():
            llm_result = load_json(cache_file)
        else:
            active_issues = [issues[idx] for idx in top_idx
                             if is_active(issues[idx], open_ms)][:3]
            llm_result    = llm_ambiguous_verdict(client, need, active_issues, open_ms)
            if llm_result:
                save_json(cache_file, llm_result)
            else:
                llm_result = {
                    "verdict":   "UNDER-PRIORITIZED",
                    "rationale": "LLM call failed; defaulted to UNDER-PRIORITIZED.",
                }
            time.sleep(0.3)

        verdict   = llm_result["verdict"]
        rationale = llm_result["rationale"]

    matched_issues = [
        {k: v for k, v in m.items() if not k.startswith("_")}
        for m in top_matches
    ]

    return {
        "cluster_id":      need["cluster_id"],
        "theme":           need["theme"],
        "need":            need["need"],
        "size":            need["size"],
        "tightness":       need["tightness"],
        "review_ids":      need["review_ids"],
        "matched_issues":  matched_issues,
        "best_similarity": best_sim,
        "verdict":         verdict,
        "rationale":       rationale,
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Match needs to GitHub issues.")
    parser.add_argument("--refresh", action="store_true",
                        help="Recompute embeddings and LLM verdicts even if cached.")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    needs      = load_json(LABELED_CLUSTERS)
    issues     = load_json(ISSUES_FILE)
    milestones = load_json(MILESTONES_FILE)
    open_ms    = open_milestone_titles(milestones)

    print(f"Loaded {len(needs)} labeled needs, {len(issues):,} GitHub issues")
    print(f"  Open milestones ({len(open_ms)}): {sorted(open_ms)}")

    model  = SentenceTransformer(EMBEDDING_MODEL)
    client = anthropic.Anthropic(api_key=api_key)
    MATCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    issue_embs = embed_issues(issues, model, refresh=args.refresh)

    print("Embedding need texts…")
    need_texts = [f"{n['theme']} {n['need']}" for n in needs]
    need_embs  = model.encode(need_texts, show_progress_bar=False)
    print(f"  {len(need_embs)} need embeddings computed")

    results = []
    for i, need in enumerate(needs):
        print(f"[{i+1:02d}/{len(needs)}] {need['cluster_id']}  {need['theme'][:40]:<42}",
              end=" ", flush=True)
        result = match_need(need, issues, need_embs[i], issue_embs,
                            open_ms, client, args.refresh)
        print(f"→ {result['verdict']:<18}  sim={result['best_similarity']:.3f}")
        results.append(result)

    save_json(OUTPUT_FILE, results)
    print(f"\nSaved {len(results)} matched needs → {OUTPUT_FILE}")

    order   = {"IGNORED": 0, "UNDER-PRIORITIZED": 1, "MISUNDERSTOOD": 2, "addressed": 3}
    sorted_ = sorted(results, key=lambda x: (order.get(x["verdict"], 9), -x["size"]))

    print("\n── Match summary ───────────────────────────────────────────────────────────────")
    print(f"{'Theme':<32} {'Verdict':<18} {'Sim':>5}  Best-match issue")
    print("─" * 100)
    for r in sorted_:
        top       = r["matched_issues"][0] if r["matched_issues"] else {}
        ms        = top.get("milestone") or "—"
        issue_str = f"#{top['issue_number']} {top['title'][:35]} [ms:{ms}]" if top else "—"
        print(f"{r['theme'][:30]:<32} {r['verdict']:<18} {r['best_similarity']:>5.3f}  {issue_str}")
    print("─" * 100)
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("  " + "  |  ".join(f"{v}: {n}" for v, n in sorted(counts.items())))
    print("─" * 100)


if __name__ == "__main__":
    main()
