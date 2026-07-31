"""
Stage 2 — Cluster

Embeds all reviews locally using sentence-transformers (all-MiniLM-L6-v2),
then clusters the embeddings with HDBSCAN to surface candidate themes.

Embeddings are cached to data/embeddings.npy — re-runs skip recomputation.
Output: data/clusters.json — one record per cluster with review IDs and tightness.

Usage:
    python src/cluster.py            # uses cached embeddings if available
    python src/cluster.py --refresh  # recomputes embeddings and clusters
"""

import argparse
import json
import numpy as np
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity
import hdbscan
import umap
from sklearn.preprocessing import normalize

# ── tunable parameters ────────────────────────────────────────────────────────
# Increase MIN_CLUSTER_SIZE to get fewer, larger clusters.
# Decrease for more, smaller clusters.
MIN_CLUSTER_SIZE = 30

# Controls noise sensitivity. Lower = more clusters, less noise.
# Higher = fewer clusters, more noise. Rule of thumb: ~1/3 of min_cluster_size.
MIN_SAMPLES = 10

# Filter out reviews shorter than this before clustering.
# Short reviews like "Good", "Nice", "Awesome" are ratings in text form — they
# contain no latent need signal and would otherwise form their own dense clusters
# that are useless for analysis.
MIN_REVIEW_CHARS = 50

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# UMAP reduces 384-dim embeddings to a lower-dimensional space before HDBSCAN.
# HDBSCAN's density estimation breaks down in high dimensions (curse of
# dimensionality — all points look equally far apart). 10 dims is a standard
# sweet spot: enough to preserve structure, small enough for HDBSCAN to work.
UMAP_N_COMPONENTS = 10
UMAP_N_NEIGHBORS  = 15   # how many neighbors UMAP considers per point
UMAP_MIN_DIST     = 0.0  # 0 = tightest possible clusters (good for HDBSCAN input)

# ── paths ─────────────────────────────────────────────────────────────────────
DATA_DIR        = Path(__file__).parent.parent / "data"
REVIEWS_FILE    = DATA_DIR / "reviews.json"
EMBEDDINGS_FILE = DATA_DIR / "embeddings.npy"
CLUSTERS_FILE   = DATA_DIR / "clusters.json"


# ── load ──────────────────────────────────────────────────────────────────────

def load_reviews() -> list[dict]:
    with open(REVIEWS_FILE, encoding="utf-8") as f:
        return json.load(f)


# ── embed ─────────────────────────────────────────────────────────────────────

def embed_reviews(reviews: list[dict], refresh: bool) -> np.ndarray:
    """
    Embed each review's text using a local sentence-transformers model.
    Cached to data/embeddings.npy so subsequent runs are instant.
    No API call — runs entirely on CPU.
    """
    if not refresh and EMBEDDINGS_FILE.exists():
        print(f"Cache hit: loading embeddings from {EMBEDDINGS_FILE}")
        embeddings = np.load(EMBEDDINGS_FILE)
        print(f"  shape={embeddings.shape}")
        return embeddings

    from sentence_transformers import SentenceTransformer

    print(f"Embedding {len(reviews):,} reviews with '{EMBEDDING_MODEL}'…")
    print("  (local CPU only — no API call, takes ~1–2 min first time)")

    model = SentenceTransformer(EMBEDDING_MODEL)
    texts = [r["text"] or "" for r in reviews]

    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)

    np.save(EMBEDDINGS_FILE, embeddings)
    print(f"  Saved → {EMBEDDINGS_FILE}  shape={embeddings.shape}")
    return embeddings


# ── dimensionality reduction ──────────────────────────────────────────────────

def reduce_dimensions(embeddings: np.ndarray) -> np.ndarray:
    """
    Reduce 384-dim sentence embeddings to UMAP_N_COMPONENTS dimensions.

    Why this step is necessary:
    HDBSCAN estimates density by looking at distances between points. In 384
    dimensions all pairwise distances converge to roughly the same value
    (curse of dimensionality), so HDBSCAN sees no density variation and marks
    everything as noise. UMAP preserves the local neighbourhood structure while
    collapsing the space to ~10 dims where density differences are meaningful.
    """
    print(f"\nReducing dimensions with UMAP: 384 → {UMAP_N_COMPONENTS} dims…")
    reducer = umap.UMAP(
        n_components=UMAP_N_COMPONENTS,
        n_neighbors=UMAP_N_NEIGHBORS,
        min_dist=UMAP_MIN_DIST,
        metric="cosine",
        random_state=42,  # fixed seed for reproducibility
    )
    reduced = reducer.fit_transform(embeddings)
    print(f"  Done. Reduced shape: {reduced.shape}")
    return reduced


# ── cluster ───────────────────────────────────────────────────────────────────

def cluster_embeddings(embeddings: np.ndarray) -> np.ndarray:
    """
    Cluster embeddings with HDBSCAN using cosine distance.

    Why HDBSCAN over k-means:
    - We don't know how many clusters exist — HDBSCAN finds them automatically.
    - Reviews that don't fit any theme get label -1 (noise) instead of being
      forced into the wrong cluster, which would corrupt our evidence.
    - It handles clusters of varying density, which is how real review themes work.
    """
    print(f"\nClustering with HDBSCAN "
          f"(min_cluster_size={MIN_CLUSTER_SIZE}, min_samples={MIN_SAMPLES}, "
          f"metric=cosine via normalized euclidean)…")

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=MIN_CLUSTER_SIZE,
        min_samples=MIN_SAMPLES,
        metric="euclidean",
        cluster_selection_method="eom",  # "excess of mass" — stable cluster edges
    )
    labels = clusterer.fit_predict(embeddings)  # expects UMAP-reduced input

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise    = int((labels == -1).sum())
    print(f"  Found {n_clusters} clusters | {n_noise:,} reviews marked as noise")
    return labels


# ── tightness ─────────────────────────────────────────────────────────────────

def compute_tightness(cluster_embeddings: np.ndarray) -> float:
    """
    Mean pairwise cosine similarity within a cluster.

    Ranges from 0 (reviews point in random directions) to 1 (all identical).
    Higher tightness = more coherent cluster = stronger evidence of one latent need.
    Stored here so Stage 5 (score.py) can use it in the confidence formula.
    """
    if len(cluster_embeddings) == 1:
        return 1.0

    sim_matrix = cosine_similarity(cluster_embeddings)

    # Upper triangle only (excluding diagonal) — avoids counting each pair twice
    # and avoids the trivial self-similarity of 1.0 inflating the score.
    n = len(cluster_embeddings)
    upper = sim_matrix[np.triu_indices(n, k=1)]
    return float(upper.mean())


# ── build cluster records ─────────────────────────────────────────────────────

def build_clusters(reviews: list[dict], embeddings: np.ndarray,
                   labels: np.ndarray) -> list[dict]:
    """
    Group reviews by their HDBSCAN label into structured cluster records.
    Noise label (-1) is excluded from the output entirely.
    Clusters are sorted by size (largest first) so the most-represented
    themes appear at the top of the output file.
    """
    # Group review indices by cluster label
    cluster_map: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        if label == -1:
            continue
        cluster_map.setdefault(int(label), []).append(idx)

    clusters = []
    for label, indices in cluster_map.items():
        c_reviews    = [reviews[i] for i in indices]
        c_embeddings = embeddings[indices]

        clusters.append({
            "cluster_id": f"c_{label:02d}",
            "review_ids": [r["id"] for r in c_reviews],
            "size":       len(c_reviews),
            "tightness":  compute_tightness(c_embeddings),
        })

    clusters.sort(key=lambda c: c["size"], reverse=True)
    return clusters


# ── summary ───────────────────────────────────────────────────────────────────

def print_summary(clusters: list[dict], reviews: list[dict], n_noise: int) -> None:
    """
    Print a table showing each cluster's ID, size, tightness, and the first
    3 review texts (truncated) so the coherence can be eyeballed quickly.
    """
    id_to_text = {r["id"]: (r["text"] or "") for r in reviews}

    print("\n── Cluster summary ──────────────────────────────────────────────────────")
    print(f"{'ID':<8} {'Size':>6} {'Tight':>7}   Preview (first 3 reviews, truncated to 80 chars)")
    print("─" * 90)

    for c in clusters:
        print(f"{c['cluster_id']:<8} {c['size']:>6} {c['tightness']:>7.3f}")
        for rid in c["review_ids"][:3]:
            snippet = id_to_text.get(rid, "")[:80].replace("\n", " ")
            print(f"         [{rid}] {snippet}…")
        print()

    total_in_clusters = sum(c["size"] for c in clusters)
    total_reviews     = total_in_clusters + n_noise

    print("─" * 90)
    print(f"  Total clusters found : {len(clusters)}")
    print(f"  Reviews in clusters  : {total_in_clusters:,} / {total_reviews:,} "
          f"({100*total_in_clusters/total_reviews:.1f}%)")
    print(f"  Reviews in noise     : {n_noise:,} "
          f"({100*n_noise/total_reviews:.1f}%)")
    print("─" * 90)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Embed and cluster reviews.")
    parser.add_argument("--refresh", action="store_true",
                        help="Recompute embeddings and clusters even if cached.")
    args = parser.parse_args()

    reviews = load_reviews()
    print(f"Loaded {len(reviews):,} reviews from {REVIEWS_FILE}")

    embeddings = embed_reviews(reviews, refresh=args.refresh)

    # Filter to substantive reviews only — short reviews like "Good" / "Nice"
    # cluster into useless identical-phrase groups. We keep the full embeddings
    # array for future use; here we just work on the meaningful subset by index.
    substantive = [(i, r) for i, r in enumerate(reviews)
                   if len(r["text"] or "") >= MIN_REVIEW_CHARS]
    sub_indices  = [i for i, _ in substantive]
    sub_reviews  = [r for _, r in substantive]
    sub_embeddings = embeddings[sub_indices]
    print(f"Filtered to {len(sub_reviews):,} substantive reviews "
          f"(≥{MIN_REVIEW_CHARS} chars) — dropped {len(reviews)-len(sub_reviews):,} short ones")

    reduced = reduce_dimensions(sub_embeddings)
    labels  = cluster_embeddings(reduced)

    n_noise  = int((labels == -1).sum())
    clusters = build_clusters(sub_reviews, sub_embeddings, labels)

    CLUSTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CLUSTERS_FILE, "w", encoding="utf-8") as f:
        json.dump(clusters, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(clusters)} clusters → {CLUSTERS_FILE}")

    print_summary(clusters, sub_reviews, n_noise)


if __name__ == "__main__":
    main()
