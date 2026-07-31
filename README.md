# Silent Stakeholder

Find unmet user needs that a product's roadmap is missing — by mining app reviews against GitHub issues.

## How to run

```bash
cp .env.example .env
# fill in ANTHROPIC_API_KEY and GITHUB_TOKEN in .env
pip install -r requirements.txt
make run
```

> **Note:** Pipeline not yet implemented. `make run` currently prints a placeholder.

## Architecture

The pipeline runs five deterministic stages. The LLM is a helper at stage 3 only — it never decides rankings or confidence scores.

1. **Ingest** — Pull app reviews from `sealuzh/app_reviews` (HuggingFace) and GitHub issues/milestones via `api.github.com`. Assign every item a stable ID.

2. **Cluster** — Embed reviews locally with `sentence-transformers`. Cluster embeddings with HDBSCAN to surface candidate themes. Cluster membership is ground truth — not LLM opinion.

3. **Label** — Call the Anthropic API (claude-sonnet-4-6) to name each cluster as a plain-language latent need. All LLM calls are cached to disk (hash → JSON) so re-runs are free.

4. **Match** — Compare each labeled theme to GitHub issues via embedding similarity. Assign a verdict from issue labels/status: `IGNORED` | `UNDER-PRIORITIZED` | `MISUNDERSTOOD`.

5. **Score** — Compute a deterministic confidence score per gap using an explicit formula (review count, cluster tightness, star severity, recency). The LLM never touches this number.

6. **Emit** — Rank gaps by confidence and write `gaps.json` with full evidence traces (review IDs + issue IDs).

## Output

`gaps.json` — top 3–5 latent needs, each with:
- `need`: plain-language description
- `confidence`: float from the formula
- `evidence`: specific review IDs + roadmap issue IDs
- `verdict`: `IGNORED` | `UNDER-PRIORITIZED` | `MISUNDERSTOOD`
