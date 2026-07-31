"""
Stage 4 — Match

For each labeled cluster (named need), find the most similar GitHub issues
and assign a verdict: IGNORED | UNDER-PRIORITIZED | MISUNDERSTOOD | addressed.

Matching uses cosine similarity between need embeddings and issue embeddings —
NOT the LLM reading 4,004 issues. The LLM is only used for the ambiguous case:
when similarity is strong AND issues are active (to decide MISUNDERSTOOD vs. addressed).

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

TOP_K = 5   # number of top issues to retrieve per need

# Cosine similarity below this → IGNORED (roadmap has nothing close to this need)
SIMILARITY_THRESHOLD = 0.35

# Issues not updated in this many days are considered stale / abandoned
STALE_DAYS = 730   # ~2 years

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
LLM_MODEL       = "claude-sonnet-4-6"

# Max characters of issue body to include in embedding text.
# all-MiniLM-L6-v2 is capped at 256 tokens; truncating body keeps the
# title signal dominant and avoids irrelevant boilerplate in long issues.
MAX_BODY_CHARS = 400

# ── paths ─────────────────────────────────────────────────────────────────────

DATA_DIR          = Path(__file__).parent.parent / "data"
LABELED_CLUSTERS  = DATA_DIR / "labeled_clusters.json"
ISSUES_FILE       = DATA_DIR / "issues.json"
ISSUE_EMBEDDINGS  = DATA_DIR / "issue_embeddings.npy"
MATCH_CACHE_DIR   = DATA_DIR / "match_cache"
OUTPUT_FILE       = DATA_DIR / "matched_needs.json"

TODAY = datetime.now(timezone.utc)


# ── data helpers ──────────────────────────────────────────────────────────────

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── issue embedding ───────────────────────────────────────────────────────────

def issue_text(issue: dict) -> str:
    """Combine title + truncated body into one string for embedding."""
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
    """Days since the issue was last updated. Returns a large number on parse failure."""
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


def is_active(issue: dict) -> bool:
    """
    An issue is active if it is open, not stale, and not stuck in triage
    without a milestone (which means it hasn't been confirmed or scheduled yet).
    """
    if issue["state"] != "open":
        return False
    if is_stale(issue):
        return False
    triage_labels = {"needs: triage", "needs triage", "triage"}
    issue_labels  = {lbl.lower() for lbl in issue.get("labels", [])}
    if triage_labels & issue_labels and not issue.get("milestone"):
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
                          active_issues: list) -> Optional[dict]:
    """
    Only called when there are active matching issues — the genuinely ambiguous case.
    Asks whether those issues address the user need or just sound related.
    """
    issue_lines = []
    for iss in active_issues:
        ms     = iss.get("milestone") or "none"
        labels = ", ".join(iss.get("labels", [])) or "none"
        body   = (iss.get("body") or "")[:200]
        issue_lines.append(
            f"  #{iss['id']}  [{iss['state']}]  milestone={ms}  labels={labels}\n"
            f"  Title: {iss['title']}\n"
            f"  Body:  {body}"
        )

    prompt = (
        f"User need (from {need['size']} app reviews):\n"
        f"  Theme: {need['theme']}\n"
        f"  Need : {need['need']}\n\n"
        f"Matching GitHub issues (active / open):\n"
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
               client: anthropic.Anthropic, refresh: bool) -> dict:
    """
    1. Compute cosine similarity between this need and every issue.
    2. Take the top-K matches.
    3. Apply rule-based verdict; call LLM only for the ambiguous case.
    """
    sims    = cosine_similarity(need_emb.reshape(1, -1), issue_embs)[0]
    top_idx = sims.argsort()[::-1][:TOP_K]

    top_matches = []
    for idx in top_idx:
        iss = issues[idx]
        top_matches.append({
            "issue_number": iss["id"],
            "title":        iss["title"],
            "similarity":   float(sims[idx]),
            "state":        iss["state"],
            "labels":       iss.get("labels", []),
            "milestone":    iss.get("milestone"),
            "updated_at":   iss.get("updated_at"),
            # internal helpers, stripped before saving
            "_stale":  is_stale(iss),
            "_active": is_active(iss),
        })

    best_sim = top_matches[0]["similarity"] if top_matches else 0.0

    # ── verdict rules ─────────────────────────────────────────────────────────

    if best_sim < SIMILARITY_THRESHOLD:
        # Rule 1: No meaningful match at all → IGNORED
        verdict   = "IGNORED"
        rationale = (f"Best match similarity {best_sim:.3f} is below threshold "
                     f"{SIMILARITY_THRESHOLD} — roadmap has no issue that covers this need.")

    elif not any(m["_active"] for m in top_matches):
        # Rule 2: Matches exist but none are currently active → UNDER-PRIORITIZED
        closed_n = sum(1 for m in top_matches if m["state"] == "closed")
        stale_n  = sum(1 for m in top_matches if m["_stale"])
        verdict   = "UNDER-PRIORITIZED"
        rationale = (f"Found {len(top_matches)} related issues (best sim {best_sim:.3f}): "
                     f"{closed_n} closed, {stale_n} stale — need exists in tracker "
                     f"but is not actively worked on.")

    else:
        # Rule 3: Active issues exist — ambiguous; LLM decides addressed vs MISUNDERSTOOD
        cid        = need["cluster_id"]
        cache_file = MATCH_CACHE_DIR / f"{cid}.json"

        if not refresh and cache_file.exists():
            llm_result = load_json(cache_file)
        else:
            # Only send the active issues to the LLM (max 3 to keep prompt tight)
            active_issues = [issues[idx] for idx in top_idx if is_active(issues[idx])][:3]
            llm_result    = llm_ambiguous_verdict(client, need, active_issues)

            if llm_result:
                save_json(cache_file, llm_result)
            else:
                # Fallback if LLM fails: treat as under-prioritized rather than crashing
                llm_result = {
                    "verdict":   "UNDER-PRIORITIZED",
                    "rationale": "LLM call failed; defaulted to UNDER-PRIORITIZED.",
                }
            time.sleep(0.3)

        verdict   = llm_result["verdict"]
        rationale = llm_result["rationale"]

    # Strip internal helpers before writing to file
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
        "review_ids":      need["review_ids"],   # evidence trace — never dropped
        "matched_issues":  matched_issues,
        "best_similarity": best_sim,
        "verdict":         verdict,
        "rationale":       rationale,
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Match needs to GitHub issues and assign verdicts.")
    parser.add_argument("--refresh", action="store_true",
                        help="Recompute embeddings and LLM verdicts even if cached.")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    needs  = load_json(LABELED_CLUSTERS)
    issues = load_json(ISSUES_FILE)
    print(f"Loaded {len(needs)} labeled needs and {len(issues):,} GitHub issues")

    model  = SentenceTransformer(EMBEDDING_MODEL)
    client = anthropic.Anthropic(api_key=api_key)
    MATCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Embed all issues (cached after first run)
    issue_embs = embed_issues(issues, model, refresh=args.refresh)

    # Embed all need texts in one batch (fast, no caching needed — 23 texts)
    print("Embedding need texts…")
    need_texts = [f"{n['theme']} {n['need']}" for n in needs]
    need_embs  = model.encode(need_texts, show_progress_bar=False)
    print(f"  {len(need_embs)} need embeddings computed")

    # Match each need
    results = []
    for i, need in enumerate(needs):
        print(f"[{i+1:02d}/{len(needs)}] {need['cluster_id']}  {need['theme'][:40]:<42}", end=" ", flush=True)
        result = match_need(need, issues, need_embs[i], issue_embs, client, args.refresh)
        print(f"→ {result['verdict']:<18}  sim={result['best_similarity']:.3f}")
        results.append(result)

    save_json(OUTPUT_FILE, results)
    print(f"\nSaved {len(results)} matched needs → {OUTPUT_FILE}")

    # ── summary table ──────────────────────────────────────────────────────────
    order   = {"IGNORED": 0, "UNDER-PRIORITIZED": 1, "MISUNDERSTOOD": 2, "addressed": 3}
    sorted_ = sorted(results, key=lambda x: (order.get(x["verdict"], 9), -x["size"]))

    print("\n── Match summary ──────────────────────────────────────────────────────────────")
    print(f"{'Theme':<32} {'Verdict':<18} {'Sim':>5}  Best-match issue")
    print("─" * 100)
    for r in sorted_:
        top       = r["matched_issues"][0] if r["matched_issues"] else {}
        issue_str = f"#{top['issue_number']} {top['title'][:42]}" if top else "—"
        print(f"{r['theme'][:30]:<32} {r['verdict']:<18} {r['best_similarity']:>5.3f}  {issue_str}")
    print("─" * 100)

    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("  " + "  |  ".join(f"{v}: {n}" for v, n in sorted(counts.items())))
    print("─" * 100)


if __name__ == "__main__":
    main()
