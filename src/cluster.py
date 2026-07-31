"""
Stage 2 — Embed reviews with a local sentence-transformers model, then
cluster with HDBSCAN to surface candidate themes.

Input:  data/reviews.json
Output: data/clusters.json  (cluster_id -> list of review IDs + centroid)
"""

# TODO: implement embed_reviews(reviews) -> np.ndarray using sentence-transformers
# TODO: implement cluster_embeddings(embeddings) -> labels array using HDBSCAN
# TODO: implement build_cluster_map(reviews, labels) -> dict
# TODO: write main() that loads reviews, embeds, clusters, and saves clusters.json
