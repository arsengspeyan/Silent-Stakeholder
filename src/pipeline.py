"""
Orchestrator — runs all five stages in order and emits gaps.json.

Usage:
    python src/pipeline.py

Stages:
    1. ingest   -> data/reviews.json, data/issues.json
    2. cluster  -> data/clusters.json
    3. label    -> data/labeled_clusters.json
    4. match    -> data/matches.json
    5. score    -> gaps.json  (top 3-5 gaps, ranked by confidence)
"""

# TODO: import and call each stage's main() in sequence
# TODO: merge outputs into a single gaps list
# TODO: rank by confidence score (code, not LLM)
# TODO: write gaps.json with full evidence traces (review IDs + issue IDs)
