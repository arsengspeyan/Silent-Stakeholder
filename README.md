# Silent Stakeholder

Find unmet user needs that a product's roadmap is missing — by mining app reviews against GitHub issues.

**App analyzed:** PPSSPP (`org.ppsspp.ppsspp`) vs `hrydgard/ppsspp` on GitHub.

## How to run

```bash
cp .env.example .env
# fill in ANTHROPIC_API_KEY and GITHUB_TOKEN in .env
pip install -r requirements.txt
make run      # build gaps.json (uses caches where available)
make qa       # AI quality tester — checks latent needs vs complaint summaries
make viewer   # open results in browser
```

Then open:
- **Results:** http://localhost:8000/viewer/ (gaps + QA grades if you ran `make qa`)
- **Guide:** http://localhost:8000/viewer/guide.html

Press `Ctrl+C` to stop the server.

To recompute everything from scratch: `make refresh`

## Architecture

Five deterministic stages. Anthropic Claude assists in three roles — it **never** decides rankings or confidence scores.

| Stage | Script | Output |
|---|---|---|
| 1. Ingest | `src/ingest.py` | `data/reviews.json`, `data/issues.json`, `data/milestones.json` |
| 2. Cluster | `src/cluster.py` | `data/clusters.json` |
| 3. Label | `src/label.py` | `data/labeled_clusters.json` |
| 4. Match | `src/match.py` | `data/matched_needs.json` |
| 5. Score | `src/score.py` | `gaps.json` |
| QA (optional) | `src/qa_gaps.py` | `data/gaps_qa.json` |

## Anthropic Claude agents (same API key)

All LLM calls use **Anthropic** (`claude-sonnet-4-6`) via `ANTHROPIC_API_KEY`. Each agent has a different job; results are cached to disk.

| Agent | Script | Role | Changes output? |
|---|---|---|---|
| **Label agent** | `src/label.py` | Names each cluster as a plain-language latent need | Yes — writes need text |
| **Match agent** | `src/match.py` | Resolves ambiguous verdicts (MISUNDERSTOOD vs addressed) | Yes — edge cases only |
| **QA critic agent** | `src/qa_gaps.py` | Tests whether gaps are latent needs vs complaint summaries | **No** — read-only QA |

```
Production:  reviews → [math cluster] → [Label agent] → [math match + Match agent] → [code score] → gaps.json
Testing:     gaps.json → [QA critic agent] → gaps_qa.json (pass / warn / fail + pitch tips)
```

Run the QA critic after the pipeline: `make qa`

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
