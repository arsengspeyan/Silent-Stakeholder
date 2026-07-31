"""
Stage 3 — Use the Anthropic API (claude-sonnet-4-6) to label each cluster with
a plain-language latent need. All calls are cached to disk keyed by input hash.

Input:  data/clusters.json + data/reviews.json
Output: data/labeled_clusters.json  (cluster_id -> {need, sample_review_ids})
"""

# TODO: implement cache_key(payload) -> str  (sha256 of JSON-serialised input)
# TODO: implement cached_llm_call(client, payload) -> dict  (read cache or call API)
# TODO: implement label_cluster(client, cluster_reviews) -> str  (the need text)
# TODO: write main() that iterates clusters, labels each, saves labeled_clusters.json
