"""
Stage 5 — Score

Assigns each gap a calibrated confidence score from an explicit formula,
then merges clusters that represent the same underlying need,
then ranks and writes gaps.json.

Formula — three signals combined by tunable weights:
  1. evidence_volume  — log-scaled review count (more reviews → more confident)
  2. cluster_tightness — mean cosine similarity within the cluster (tighter → more coherent)
  3. gap_clarity      — how clearly the roadmap misses this need (derived from verdict)

Merge groups are explicit constants near the top — every merge is documented
with a reason so the editorial decision is auditable, not hidden.

Usage:
    python src/score.py
"""

import json
import math
from pathlib import Path

# ── tunable weights ───────────────────────────────────────────────────────────
# Must sum to 1.0 for the output to be a clean 0–100% score.
# Rationale for defaults:
#   GAP    0.45 — whether the roadmap misses this is the most important question
#   VOLUME 0.35 — raw user demand matters a lot; log-scaled so big clusters don't dominate
#   TIGHT  0.20 — coherence is useful but a loose cluster with 200 reviews still counts

WEIGHT_VOLUME    = 0.35
WEIGHT_TIGHTNESS = 0.20
WEIGHT_GAP       = 0.45

assert abs(WEIGHT_VOLUME + WEIGHT_TIGHTNESS + WEIGHT_GAP - 1.0) < 1e-9, \
    "Weights must sum to 1.0"

# Verdict → gap clarity value.
VERDICT_GAP_CLARITY = {
    "IGNORED":           1.00,
    "UNDER-PRIORITIZED": 0.80,
    "MISUNDERSTOOD":     0.60,
    "addressed":         0.00,  # not a gap — excluded before scoring
}

# Clusters explicitly dropped from final output (non-substantive filler).
# c_19 ("Review quality signal") is junk — generic encouragement, not a real need.
EXCLUDED_CLUSTERS = {"c_19"}

# ── merge groups ──────────────────────────────────────────────────────────────
# Clusters that represent the same underlying user need, identified by human
# review of the labeled output. Each group is merged into one entry.
# "clusters" — the cluster IDs to combine (union of review_ids, pooled evidence).
# "theme"    — the unified theme name for the merged entry.
# "reason"   — why these clusters were merged (judge-facing rationale).

MERGE_GROUPS = [
    {
        "theme":    "Game acquisition guidance",
        "clusters": ["c_18", "c_06"],
        "reason":   (
            "Both clusters express the same need: users cannot find or load game "
            "files into the emulator. c_18 (224 reviews) focuses on confusion about "
            "where to get games; c_06 (85 reviews) focuses on not understanding the "
            "loading flow. Same root cause, same fix."
        ),
    },
    {
        "theme":    "Games run poorly (performance & compatibility)",
        "clusters": ["c_09", "c_20", "c_22"],
        "reason":   (
            "Three facets of the same underlying need: games lag, stutter, or fail "
            "to run on users' devices. c_09 (232 reviews) — game compatibility "
            "inconsistency; c_20 (175 reviews) — general emulator slowness; "
            "c_22 (106 reviews) — frame-rate lag. All point to the same gap: "
            "smooth, reliable emulation across a wider range of hardware."
        ),
    },
]

# Number of headline gaps to surface as primary findings.
TOP_N = 5

# ── paths ─────────────────────────────────────────────────────────────────────
DATA_DIR     = Path(__file__).parent.parent / "data"
MATCHED_FILE = DATA_DIR / "matched_needs.json"
OUTPUT_FILE  = Path(__file__).parent.parent / "gaps.json"


# ── helpers ───────────────────────────────────────────────────────────────────

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── formula ───────────────────────────────────────────────────────────────────

def norm_volume(review_count: int, max_count: int) -> float:
    """
    Normalize review count to [0, 1] using log scaling.
    Capped at 1.0 so merged groups that exceed the original max don't break the scale.
    """
    if max_count <= 0:
        return 0.0
    return min(1.0, math.log1p(review_count) / math.log1p(max_count))


def compute_confidence(review_count: int, tightness: float,
                       verdict: str, max_count: int) -> tuple:
    """
    Returns (score_float, breakdown_dict).
    Accepts primitives (not a need dict) so it works for both raw and merged gaps.
    """
    vol   = norm_volume(review_count, max_count)
    tight = tightness
    gap   = VERDICT_GAP_CLARITY[verdict]

    score = WEIGHT_VOLUME * vol + WEIGHT_TIGHTNESS * tight + WEIGHT_GAP * gap

    breakdown = {
        "volume_score":  round(vol,   4),
        "tightness":     round(tight, 4),
        "gap_clarity":   round(gap,   4),
        "weights": {
            "volume":    WEIGHT_VOLUME,
            "tightness": WEIGHT_TIGHTNESS,
            "gap":       WEIGHT_GAP,
        },
        "formula": (
            f"({WEIGHT_VOLUME} × {vol:.4f})  "
            f"+ ({WEIGHT_TIGHTNESS} × {tight:.4f})  "
            f"+ ({WEIGHT_GAP} × {gap:.4f})  "
            f"= {score:.4f}"
        ),
    }
    return round(score, 4), breakdown


# ── merge logic ───────────────────────────────────────────────────────────────

def apply_merges(gaps: list, max_count_pre: int) -> tuple:
    """
    Combine clusters listed in MERGE_GROUPS into single entries.
    Returns (merged_gaps, new_max_count, merge_log).

    merge_log is a list of dicts describing each merge for the before/after display.
    """
    # Build lookup by cluster_id
    by_id = {g["cluster_id"]: g for g in gaps}

    # Track which cluster_ids are absorbed into a group
    absorbed = set()
    merged   = []
    merge_log = []

    for group in MERGE_GROUPS:
        members = [by_id[cid] for cid in group["clusters"] if cid in by_id]
        if not members:
            continue

        # Union of review_ids (set to deduplicate just in case)
        all_review_ids = list(dict.fromkeys(
            rid for m in members for rid in m["evidence"]["review_ids"]
        ))

        # Union of matched issue numbers (preserve order, deduplicate)
        seen_issues = {}
        for m in members:
            for iss_num in m["evidence"]["matched_issue_numbers"]:
                if iss_num not in seen_issues:
                    seen_issues[iss_num] = True
        all_issue_numbers = list(seen_issues.keys())

        # Weighted-average tightness (weighted by original cluster size)
        total_size = sum(m["review_count"] for m in members)
        avg_tight  = sum(m["tightness"] * m["review_count"] for m in members) / total_size

        # Verdict: if all the same, use it; if mixed, use the one with highest gap clarity
        verdicts = list(dict.fromkeys(m["verdict"] for m in members))
        if len(verdicts) == 1:
            merged_verdict = verdicts[0]
        else:
            merged_verdict = max(verdicts, key=lambda v: VERDICT_GAP_CLARITY.get(v, 0))

        # Use the largest cluster's need text (has the most evidence behind it)
        primary = max(members, key=lambda m: m["review_count"])

        # Top issue: highest-similarity across all members
        all_top_issues = [m["top_issue"] for m in members if m.get("top_issue")]
        best_top_issue = (
            max(all_top_issues, key=lambda i: i.get("similarity", 0))
            if all_top_issues else None
        )

        merged_review_count = len(all_review_ids)
        new_score, new_breakdown = compute_confidence(
            merged_review_count, avg_tight, merged_verdict, max_count_pre
        )

        merged_entry = {
            "cluster_id":           f"merged({'_'.join(group['clusters'])})",
            "merged_from":          group["clusters"],
            "merge_reason":         group["reason"],
            "theme":                group["theme"],
            "need":                 primary["need"],
            "verdict":              merged_verdict,
            "verdicts_by_cluster":  {m["cluster_id"]: m["verdict"] for m in members},
            "confidence":           new_score,
            "confidence_pct":       f"{new_score * 100:.1f}%",
            "confidence_breakdown": new_breakdown,
            "evidence": {
                "review_ids":            all_review_ids,
                "matched_issue_numbers": all_issue_numbers,
            },
            "review_count": merged_review_count,
            "tightness":    round(avg_tight, 4),
            "top_issue":    best_top_issue,
        }

        merge_log.append({
            "group":         group["theme"],
            "clusters":      [(m["cluster_id"], m["theme"], m["review_count"],
                               m["confidence_pct"], m["verdict"]) for m in members],
            "merged_count":  merged_review_count,
            "merged_conf":   merged_entry["confidence_pct"],
            "merged_verdict": merged_verdict,
        })

        merged.append(merged_entry)
        absorbed.update(group["clusters"])

    # Keep unmerged gaps unchanged
    unmerged = [g for g in gaps if g["cluster_id"] not in absorbed]

    # New max count might be larger due to merged review pools
    all_combined = merged + unmerged
    new_max = max(g["review_count"] for g in all_combined) if all_combined else 1

    # If any merged group's count exceeds the pre-merge max, recompute their scores
    if new_max > max_count_pre:
        for entry in merged:
            s, b = compute_confidence(
                entry["review_count"], entry["tightness"],
                entry["verdict"], new_max
            )
            entry["confidence"]           = s
            entry["confidence_pct"]       = f"{s * 100:.1f}%"
            entry["confidence_breakdown"] = b

    return merged + unmerged, new_max, merge_log


# ── display helpers ───────────────────────────────────────────────────────────

def print_gap_table(gaps: list, title: str, n: int = None) -> None:
    subset = gaps[:n] if n else gaps
    print(f"\n── {title} {'─' * max(0, 75 - len(title))}")
    print(f"{'':2} {'Rk':<3} {'Theme':<34} {'Verdict':<18} {'Conf':>6} {'N':>5}  Clusters")
    print("─" * 100)
    for g in subset:
        star = "★" if g.get("headline") else " "
        cids = ", ".join(g.get("merged_from", [g["cluster_id"]]))
        print(f"{star} {g['rank']:<3} {g['theme'][:32]:<34} {g['verdict']:<18} "
              f"{g['confidence_pct']:>6}  {g['review_count']:>4}  {cids}")
    print("─" * 100)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    matched = load_json(MATCHED_FILE)

    # Drop excluded clusters and non-gaps
    candidates = [
        n for n in matched
        if n["cluster_id"] not in EXCLUDED_CLUSTERS
        and n["verdict"] != "addressed"
    ]
    print(f"Loaded {len(matched)} matched needs → {len(candidates)} gap candidates "
          f"(dropped {len(matched) - len(candidates)})")

    max_count_pre = max(n["size"] for n in candidates) if candidates else 1

    # Score every candidate individually
    gaps_pre = []
    for need in candidates:
        score, breakdown = compute_confidence(
            need["size"], need["tightness"], need["verdict"], max_count_pre
        )
        gaps_pre.append({
            "cluster_id":           need["cluster_id"],
            "theme":                need["theme"],
            "need":                 need["need"],
            "verdict":              need["verdict"],
            "confidence":           score,
            "confidence_pct":       f"{score * 100:.1f}%",
            "confidence_breakdown": breakdown,
            "evidence": {
                "review_ids":            need["review_ids"],
                "matched_issue_numbers": [m["issue_number"] for m in need.get("matched_issues", [])],
            },
            "review_count": need["size"],
            "tightness":    need["tightness"],
            "rationale":    need.get("rationale", ""),
            "top_issue":    need["matched_issues"][0] if need.get("matched_issues") else None,
        })

    gaps_pre.sort(key=lambda g: g["confidence"], reverse=True)
    for i, g in enumerate(gaps_pre):
        g["rank"] = i + 1

    # ── BEFORE table ──────────────────────────────────────────────────────────
    print_gap_table(gaps_pre, "BEFORE merge — top 10 pre-merge gaps", n=10)

    # ── Apply merges ──────────────────────────────────────────────────────────
    print("\n── Merges being applied ─────────────────────────────────────────────────────")
    gaps_post, max_count_post, merge_log = apply_merges(gaps_pre, max_count_pre)

    for log in merge_log:
        print(f"\n  Group: \"{log['group']}\"  (merged verdict: {log['merged_verdict']})")
        for cid, theme, n, conf, verdict in log["clusters"]:
            print(f"    {cid}  {theme[:40]:<42} {n:>4} reviews  {conf}  {verdict}")
        print(f"    → merged: {log['merged_count']} reviews  {log['merged_conf']}")

    # Re-rank after merge
    gaps_post.sort(key=lambda g: g["confidence"], reverse=True)
    for i, g in enumerate(gaps_post):
        g["rank"]     = i + 1
        g["headline"] = i < TOP_N

    headline = [g for g in gaps_post if g["headline"]]

    # ── AFTER table ───────────────────────────────────────────────────────────
    print_gap_table(gaps_post, "AFTER merge — full ranked list")

    # ── Confidence breakdown for top 3 ────────────────────────────────────────
    print("\n── Confidence breakdown — top 3 (post-merge) ───────────────────────────────")
    for g in gaps_post[:3]:
        b = g["confidence_breakdown"]
        print(f"\n  #{g['rank']} {g['theme']}  ({g['confidence_pct']})")
        print(f"     {b['formula']}")
        print(f"     volume={b['volume_score']}  tightness={b['tightness']}  gap_clarity={b['gap_clarity']}")
        if g.get("merged_from"):
            print(f"     merged from: {g['merged_from']}  ({g['review_count']} reviews combined)")
    print()

    # ── Save ──────────────────────────────────────────────────────────────────
    output = {
        "headline_gaps": headline,
        "all_gaps":      gaps_post,
        "meta": {
            "total_gaps":          len(gaps_post),
            "headline_count":      TOP_N,
            "merge_groups":        MERGE_GROUPS,
            "weights": {
                "volume":    WEIGHT_VOLUME,
                "tightness": WEIGHT_TIGHTNESS,
                "gap":       WEIGHT_GAP,
            },
            "verdict_gap_clarity": VERDICT_GAP_CLARITY,
            "excluded_clusters":   sorted(EXCLUDED_CLUSTERS),
        },
    }

    save_json(OUTPUT_FILE, output)
    print(f"Saved → {OUTPUT_FILE}")
    print(f"  Headline gaps: {len(headline)}  |  Total ranked: {len(gaps_post)}")


if __name__ == "__main__":
    main()
