# Silent Stakeholder

Find unmet user needs that a product's roadmap is missing — by mining app reviews against GitHub issues.

**App analyzed:** PPSSPP (`org.ppsspp.ppsspp`) vs `hrydgard/ppsspp` on GitHub.

---

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| **Python 3.9+** | `python3 --version` |
| **pip** | Install dependencies (see Step 1) |
| **ANTHROPIC_API_KEY** | Required for Label, Match, and QA stages ([console.anthropic.com](https://console.anthropic.com)) |
| **GITHUB_TOKEN** | Required on first ingest to fetch issues ([github.com/settings/tokens](https://github.com/settings/tokens)) — read-only `public_repo` is enough |
| **Network** | First run downloads HuggingFace reviews + GitHub data (~1–2 min) |

---

## Quick start (full pipeline)

From the project root:

```bash
# 1. One-time setup
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY and GITHUB_TOKEN

make install          # pip install -r requirements.txt

# 2. Build the report
make run              # → gaps.json (uses caches on repeat runs)

# 3. Optional: AI quality check on headline gaps
make qa               # → data/gaps_qa.json (pass / warn / fail)

# 4. Open the UI
make viewer           # → http://localhost:8000/viewer/
```

Press **Ctrl+C** in the terminal to stop the viewer server.

---

## Execution steps (what each command does)

### Step 1 — Install dependencies (once)

```bash
make install
# same as: pip3 install -r requirements.txt
```

Installs: `datasets`, `sentence-transformers`, `scikit-learn`, `hdbscan`, `umap-learn`, `anthropic`, `requests`, `python-dotenv`.

First clustering run also downloads the embedding model (`all-MiniLM-L6-v2`, ~90 MB, cached locally).

---

### Step 2 — Configure secrets (once)

```bash
cp .env.example .env
```

Edit `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
```

`.env` is gitignored — never commit it.

---

### Step 3 — Run the pipeline

```bash
make run
# same as: python3 src/pipeline.py
```

Runs five stages in order:

| # | Stage | Script | Needs API? | Output file |
|---|-------|--------|------------|-------------|
| 1 | **Ingest** | `src/ingest.py` | GitHub token (first fetch) | `data/reviews.json`, `data/issues.json`, `data/milestones.json` |
| 2 | **Cluster** | `src/cluster.py` | No (local CPU) | `data/clusters.json` |
| 3 | **Label** | `src/label.py` | Anthropic | `data/labeled_clusters.json` |
| 4 | **Match** | `src/match.py` | Anthropic (edge cases only) | `data/matched_needs.json` |
| 5 | **Score** | `src/score.py` | No | **`gaps.json`** |

**Timing (with warm caches):** ~30 seconds total.  
**First run:** ~2–5 minutes (download reviews, embed 9,771 texts, LLM calls).

**Re-run from scratch** (ignore all caches):

```bash
make refresh
# same as: python3 src/pipeline.py --refresh
```

**Resume from a specific stage** (if an earlier stage already succeeded):

```bash
python3 src/pipeline.py --from label
python3 src/pipeline.py --from match
python3 src/pipeline.py --from score   # score has no --refresh flag
```

---

### Step 4 — QA critic (optional)

```bash
make qa
# same as: python3 src/qa_gaps.py
```

Reads the top 5 headline gaps from `gaps.json` and grades each:
- **pass** / **warn** / **fail** — latent need vs complaint summary
- Does **not** change scores or ranking

Output: `data/gaps_qa.json`

Requires `gaps.json` and `ANTHROPIC_API_KEY`.

---

### Step 5 — View results

```bash
make viewer
```

This command:
1. Checks `gaps.json` exists
2. Copies `gaps.json` → `viewer/gaps.json`
3. Copies `data/gaps_qa.json` → `viewer/gaps_qa.json` (if you ran `make qa`)
4. Starts a local server on port **8000**

Open in browser:

| URL | What you see |
|-----|--------------|
| http://localhost:8000/viewer/ | Results dashboard — gaps, formula, evidence, QA badges |
| http://localhost:8000/viewer/guide.html | Presentation guide (14 slides) |

The viewer is **read-only** — no pipeline or AI runs at display time.

> **Important:** Run `make viewer` from the **project root**, not from inside `viewer/`.

---

## Fast demo (skip pipeline)

The repo includes a pre-built `gaps.json`. To view results without running the pipeline:

```bash
make viewer
```

You get the ranked gaps immediately. Run `make run` when you want to recompute from source data.

---

## Verify everything worked

After `make run`, check:

```bash
# Main output exists
test -f gaps.json && echo "gaps.json OK"

# Pipeline intermediates (gitignored, local only)
ls data/reviews.json data/clusters.json data/labeled_clusters.json data/matched_needs.json

# Quick sanity check
python3 -c "import json; g=json.load(open('gaps.json')); print(len(g['headline_gaps']), 'headline gaps,', g['meta']['total_gaps'], 'total ranked')"
```

Expected output: **`5 headline gaps, 18 total ranked`**

Current top gap: **Games run poorly (performance & compatibility) — 81.3%**

---

## Makefile reference

| Command | What it does |
|---------|--------------|
| `make install` | Install Python dependencies |
| `make run` | Full pipeline → `gaps.json` |
| `make refresh` | Full pipeline, ignore all caches |
| `make qa` | QA critic on headline gaps → `data/gaps_qa.json` |
| `make viewer` | Copy JSON to viewer + serve on :8000 |

---

## Architecture

Five deterministic stages. Anthropic Claude assists in three roles — it **never** decides rankings or confidence scores.

```
Reviews (HuggingFace)  ──┐
                         ├──► Ingest → Cluster → Label → Match → Score → gaps.json
GitHub (issues)        ──┘                                              │
                                                                        ├──► Viewer
                                                                        └──► QA critic (optional)
```

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

## Confidence formula

```
confidence = (0.35 × volume) + (0.20 × tightness) + (0.45 × gap_clarity)
```

- **Volume** — log-scaled review count
- **Tightness** — mean similarity within cluster
- **Gap clarity** — IGNORED=1.0, UNDER-PRIORITIZED=0.8, MISUNDERSTOOD=0.6

Defined in `src/score.py`. Every score in `gaps.json` includes the full formula breakdown.

## Output

`gaps.json` — top 5 headline gaps + 18 ranked total, each with:
- `need` — plain-language latent need
- `confidence` / `confidence_pct` — from the formula
- `confidence_breakdown.formula` — auditable calculation string
- `evidence.review_ids` + `evidence.matched_issue_numbers`
- `verdict` — `IGNORED` | `UNDER-PRIORITIZED` | `MISUNDERSTOOD`

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `gaps.json not found` | Run `make run` first |
| GitHub API errors on ingest | Check `GITHUB_TOKEN` in `.env` |
| Anthropic errors on label/match/qa | Check `ANTHROPIC_API_KEY` in `.env` |
| Viewer shows empty / 404 on gaps | Run `make viewer` from **project root**, not `viewer/` |
| QA badges missing in UI | Run `make qa` then `make viewer` again |
| Port 8000 already in use | Stop other server or change port in `Makefile` |
| Slow first cluster run | Normal — embedding 9,771 reviews takes ~1–2 min; cached after |

## More docs

| File | Purpose |
|------|---------|
| `DEFENSE.md` | Judge Q&A with exact numbers |
| `EXPLANATION.md` | Full pipeline walkthrough |
| `PITCH.md` | Markdown pitch deck |
| `ABOUT.md` | Project overview |

## Live defense

See `DEFENSE.md` for judge Q&A with exact numbers from the output.
