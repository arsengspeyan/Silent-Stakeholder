"""
Stage 5 — Compute a deterministic confidence score for each gap.

Formula components (code decides weights, not the LLM):
  - review_count:     number of reviews in the cluster
  - cluster_tightness: mean cosine similarity to centroid
  - star_severity:    proportion of 1-2 star reviews in cluster
  - recency:          fraction of reviews from the last 12 months

Output: float in [0, 1] for each cluster.
"""

# TODO: implement compute_confidence(cluster_meta) -> float  (explicit formula)
# TODO: document the formula with inline comments so judges can audit it
