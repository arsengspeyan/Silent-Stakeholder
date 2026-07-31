# Silent Stakeholder

Find unmet user needs that a product's roadmap is missing — by mining app reviews against GitHub issues.

**App analyzed:** PPSSPP (`org.ppsspp.ppsspp`) vs `hrydgard/ppsspp` on GitHub.

## How to run

```bash
cp .env.example .env
# fill in ANTHROPIC_API_KEY and GITHUB_TOKEN in .env
pip install -r requirements.txt
make run      # build gaps.json (uses caches where available)
make viewer   # open results in browser
```

Then open:
- **Results:** http://localhost:8000/viewer/
- **Guide:** http://localhost:8000/viewer/guide.html

Press `Ctrl+C` to stop the server.

To recompute everything from scratch: `make refresh`

## Architecture

Five deterministic stages. The LLM names clusters and helps with ambiguous verdicts — it **never** decides rankings or confidence scores.

| Stage | Script | Output |
|---|---|---|
| 1. Ingest | `src/ingest.py` | `data/reviews.json`, `data/issues.json`, `data/milestones.json` |
| 2. Cluster | `src/cluster.py` | `data/clusters.json` |
| 3. Label | `src/label.py` | `data/labeled_clusters.json` |
| 4. Match | `src/match.py` | `data/matched_needs.json` |
| 5. Score | `src/score.py` | `gaps.json` |

## Confidence formula

```
confidence = (0.35 × volume) + (0.20 × tightness) + (0.45 × gap_clarity)
```

- **Volume** — log-scaled review count
- **Tightness** — mean similarity within cluster
- **Gap clarity** — IGNORED=1.0, UNDER-PRIORITIZED=0.8, MISUNDERSTOOD=0.6

Defined in `src/score.py`. Every score in `gaps.json` includes the full formula breakdown.

## Output

`gaps.json` — top 5 headline gaps + 19 ranked total, each with:
- `need` — plain-language latent need
- `confidence` / `confidence_pct` — from the formula
- `confidence_breakdown.formula` — auditable calculation string
- `evidence.review_ids` + `evidence.matched_issue_numbers`
- `verdict` — `IGNORED` | `UNDER-PRIORITIZED` | `MISUNDERSTOOD`

## Live defense

See `DEFENSE.md` for judge Q&A with exact numbers from the output.
