"""
Stage 3 — Label

Uses the Anthropic API (claude-sonnet-4-6) to assign each cluster a plain-language
latent-need label. The LLM only names clusters — it does NOT decide gaps, confidence,
or verdicts. Those are handled by code in later stages.

Every API call is cached to data/label_cache/<cluster_id>.json so re-runs are free
and reproducible. On re-run, already-cached clusters are skipped automatically.

Usage:
    python src/label.py            # skips already-cached clusters
    python src/label.py --refresh  # re-labels all clusters from scratch
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from typing import Optional

# ── constants ─────────────────────────────────────────────────────────────────

MODEL       = "claude-sonnet-4-6"
MAX_SAMPLES = 20   # max reviews sent to the LLM per cluster call

DATA_DIR        = Path(__file__).parent.parent / "data"
CLUSTERS_FILE   = DATA_DIR / "clusters.json"
REVIEWS_FILE    = DATA_DIR / "reviews.json"
LABEL_CACHE_DIR = DATA_DIR / "label_cache"
OUTPUT_FILE     = DATA_DIR / "labeled_clusters.json"


# ── helpers ───────────────────────────────────────────────────────────────────

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── sampling ──────────────────────────────────────────────────────────────────

def sample_reviews(cluster: dict, id_to_review: dict) -> list[dict]:
    """
    Pick up to MAX_SAMPLES reviews from the cluster.
    Sorted by text length descending so longer, more substantive reviews are
    preferred — they carry more latent-need signal than short ones.
    """
    reviews = [id_to_review[rid] for rid in cluster["review_ids"]
               if rid in id_to_review]

    # Prefer longer reviews: more words = more context for the LLM to work with
    reviews.sort(key=lambda r: len(r.get("text") or ""), reverse=True)

    return reviews[:MAX_SAMPLES]


# ── prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an analyst identifying latent user needs from app reviews.

A "latent need" is what users actually need — stated in plain language — even if they
never used those exact words. It is NOT a complaint summary. It is the underlying
need that multiple complaints point to.

You will receive a batch of reviews from the same cluster (they were grouped together
by a machine-learning algorithm because they are semantically similar).

Return ONLY valid JSON with exactly these three keys:
  "need"    — one sentence stating the latent need from the user's perspective
               (what they need, not what they complained about)
  "theme"   — 2 to 4 words: a short label (e.g. "Audio sync lag", "Controller remapping")
  "summary" — one sentence describing the evidence pattern across the reviews

Rules:
- No prose before or after the JSON
- No markdown
- No code fences (no ```)
- Raw JSON only
- Do not invent needs that are not supported by the reviews\
"""


def build_user_prompt(cluster: dict, sample: list[dict]) -> str:
    lines = [
        f"Cluster ID: {cluster['cluster_id']}",
        f"Total cluster size: {cluster['size']} reviews (showing {len(sample)} samples)",
        "",
    ]
    for r in sample:
        stars = r.get("stars", "?")
        text  = (r.get("text") or "").strip()
        lines.append(f"[{r['id']} | {stars}★] {text}")
    return "\n".join(lines)


# ── LLM call + parsing ────────────────────────────────────────────────────────

def parse_label(raw: str) -> dict:
    """
    Strip optional ```json ... ``` fences then JSON-parse.
    Raises ValueError / json.JSONDecodeError if parsing fails.
    """
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned.strip())
    return json.loads(cleaned)


def label_cluster(client: anthropic.Anthropic, cluster: dict,
                  sample: list[dict]) -> Optional[dict]:
    """
    Make one API call to label a single cluster.
    Returns the parsed label dict, or None on any failure (so the run continues).
    """
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(cluster, sample)}],
        )
        raw = response.content[0].text
    except Exception as e:
        print(f"\n  API error for {cluster['cluster_id']}: {e}")
        return None

    try:
        label = parse_label(raw)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"\n  JSON parse error for {cluster['cluster_id']}: {e}")
        print(f"  Raw response was: {raw[:300]}")
        return None

    # Make sure all expected fields are present
    for field in ("need", "theme", "summary"):
        if field not in label:
            print(f"\n  Missing field '{field}' in response for {cluster['cluster_id']} — skipping")
            return None

    return label


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Label clusters using the Anthropic API.")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-label all clusters even if already cached.")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)

    clusters     = load_json(CLUSTERS_FILE)
    reviews      = load_json(REVIEWS_FILE)
    id_to_review = {r["id"]: r for r in reviews}

    print(f"Loaded {len(clusters)} clusters and {len(reviews):,} reviews")
    LABEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    client  = anthropic.Anthropic(api_key=api_key)
    labeled = []
    hits    = 0
    failed  = 0

    for cluster in clusters:
        cid        = cluster["cluster_id"]
        cache_file = LABEL_CACHE_DIR / f"{cid}.json"

        if not args.refresh and cache_file.exists():
            # Re-use the cached label — no API call
            label = load_json(cache_file)
            hits += 1
        else:
            sample = sample_reviews(cluster, id_to_review)
            print(f"  {cid}  size={cluster['size']:>3}  sample={len(sample):>2} … ", end="", flush=True)

            label = label_cluster(client, cluster, sample)
            if label is None:
                failed += 1
                continue

            save_json(cache_file, label)
            print(f"\"{label['theme']}\"")

            # Small pause — keeps us comfortably inside API rate limits
            time.sleep(0.5)

        labeled.append({
            "cluster_id": cid,
            "size":       cluster["size"],
            "tightness":  cluster["tightness"],
            "review_ids": cluster["review_ids"],   # evidence trace — never dropped
            "need":       label["need"],
            "theme":      label["theme"],
            "summary":    label["summary"],
        })

    save_json(OUTPUT_FILE, labeled)

    print(f"\nSaved {len(labeled)} labeled clusters → {OUTPUT_FILE}")
    if hits:
        print(f"  Cache hits (no API call): {hits}")
    if failed:
        print(f"  WARNING: {failed} cluster(s) failed to label")

    # ── summary table ──────────────────────────────────────────────────────────
    print("\n── Label summary ──────────────────────────────────────────────────────")
    print(f"{'Theme':<30} {'Size':>5} {'Tight':>7}  Need (truncated to 55 chars)")
    print("─" * 95)
    for c in sorted(labeled, key=lambda x: x["size"], reverse=True):
        theme = c["theme"][:28]
        need  = c["need"][:55]
        print(f"{theme:<30} {c['size']:>5} {c['tightness']:>7.3f}  {need}…")
    print("─" * 95)


if __name__ == "__main__":
    main()
