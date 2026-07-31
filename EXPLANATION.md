# What We Built So Far — Simple Explanation

## The Big Idea

Imagine you are the product manager of a popular app. You have thousands of user reviews on the Play Store AND a list of planned features on GitHub. The question is:

> **"Are we building the right things? What do users actually need that we are NOT working on?"**

That is exactly what this project does. It reads both sides — user reviews and the development roadmap — and finds the gaps: real user needs that the team is ignoring, under-prioritizing, or misunderstanding.

We call it **Silent Stakeholder** because the users are stakeholders in the product, but nobody is listening to them systematically.

---

## What Makes This Different From a Simple Review Summarizer?

A review summarizer just tells you "people complain about crashes" or "users want dark mode."

We go deeper. We find **latent needs** — patterns hiding across hundreds of reviews that users never stated directly. For example:

- Users don't say "I need offline save-state sync across devices."
- But they DO say things like "I lost my progress when I switched phones," "my saves disappeared after an update," "wish I could continue on my tablet."
- Our system clusters those reviews together and concludes: users have an **unmet need around cross-device save continuity** — something the roadmap might completely ignore.

---

## The App We Chose: PPSSPP

PPSSPP is a free, open-source PlayStation Portable emulator. It is available on F-Droid (an app store for open-source Android apps) and on Google Play.

Why we chose it:
- It has **9,771 user reviews** in our dataset — one of the largest sets available for an open-source app.
- Its GitHub repository (`hrydgard/ppsspp`) uses real GitHub Issues for bug tracking and feature requests, with **70 milestones** (planned releases).
- It is a complex app with real user pain points around performance, game compatibility, and controls — fertile ground for finding unmet needs.

---

## The Key Principle We Never Break

> **The AI (Claude) is a helper, not the decision-maker.**

Here is exactly what the AI does and does NOT do in this pipeline:

| Task | Who does it |
|---|---|
| Grouping similar reviews | **Algorithm** (HDBSCAN clustering) |
| Naming what each group is about | **AI** (Claude reads the reviews and writes a plain-language label) |
| Comparing groups to the roadmap | **Algorithm** (embedding similarity) |
| Deciding the verdict (IGNORED / UNDER-PRIORITIZED / MISUNDERSTOOD) | **Rules in code** (based on issue labels and status) |
| Calculating the confidence score | **Formula in code** (never the AI's opinion) |
| Ranking the final gaps | **Code** (sorts by confidence number) |

The AI never gets to say "I think this is a 0.87 confidence gap." The formula does that, and the formula is written out explicitly so anyone can audit it.

---

## Stage 1 — Ingest (`src/ingest.py`) ✅ Done

Before we can find gaps, we need data. This stage pulls both sides of the pipeline.

### Side 1 — User Reviews (`data/reviews.json`)

We used a public dataset on HuggingFace called `sealuzh/app_reviews`. It contains Play Store reviews for hundreds of apps.

**What we did:**
1. Downloaded the full dataset (288,065 reviews total across all apps)
2. Filtered to only PPSSPP reviews → **9,771 reviews**
3. Sorted them by date + text so the order is always the same
4. Assigned each review a stable ID like `rev_0001`, `rev_0002`, etc.

**Why stable IDs matter:** Every review ID is our "evidence receipt." When we say "users need better audio sync," we can point to specific reviews like `rev_0342`, `rev_1891`, `rev_4420` that prove it. Judges can check.

Each review record looks like this:
```json
{
  "id": "rev_0063",
  "package_name": "org.ppsspp.ppsspp",
  "text": "Love it... But sound is lagging fix that nd it will be awesome...",
  "date": "2017-08-14",
  "stars": 4
}
```

### Side 2 — GitHub Roadmap (`data/issues.json` + `data/milestones.json`)

We connected to the GitHub API to pull everything the PPSSPP team has planned or is working on.

**What we did:**
1. Pulled all GitHub Issues (open AND closed) — **9,900 raw records**
2. Filtered out Pull Requests (code submissions) — the GitHub API mixes them in with issues, but we only want feature requests and bug reports
3. Kept **4,004 real issues**
4. Also pulled all **70 milestones** (the team's release plans)

**Why we filter PRs:** Pull Requests are code changes submitted by contributors. They are not the same as issues (user-reported problems or feature requests). Mixing them in would pollute our roadmap understanding.

### Smart Caching

Every time you run the pipeline, it checks: "Do the data files already exist?" If yes, it skips the download. First run takes a minute or two; every run after is instant. Pass `--refresh` to force a re-fetch.

---

## Stage 2 — Cluster (`src/cluster.py`) ✅ Done

Now we have 9,771 reviews. The next step is grouping them so that reviews about the same underlying problem end up together.

### Step 1 — Filter short reviews

First we throw away reviews shorter than 50 characters — things like "Good", "Nice", "Awesome". These are ratings disguised as text. They contain zero information about what users actually need. After filtering: **2,905 substantive reviews** remain.

### Step 2 — Embed the reviews

We convert each review into a list of 384 numbers called an **embedding** (or vector). This is done locally on your computer using a library called `sentence-transformers` with the model `all-MiniLM-L6-v2`. No API call is made here — it runs entirely offline.

Two reviews that talk about the same thing will produce similar numbers. Two reviews about completely different things will produce very different numbers. This is how meaning becomes math.

The embeddings are cached to `data/embeddings.npy`. Re-runs skip this step entirely.

### Step 3 — Reduce dimensions with UMAP

Each review is now a point in 384-dimensional space. The problem: in very high dimensions, all points look equally far apart (this is called the **curse of dimensionality**). HDBSCAN needs to find areas of density to form clusters, but in 384 dimensions there is no visible density variation.

We use a tool called **UMAP** to compress the 384 dimensions down to just 10, while preserving which reviews are close to each other. Think of it like squishing a complex 3D shape into a 2D map — you lose some detail but the important structure remains.

After UMAP: each review is a point in 10-dimensional space, and the density variation is now visible to the clustering algorithm.

### Step 4 — Cluster with HDBSCAN

**HDBSCAN** finds natural groupings (clusters) in the data without being told how many clusters to look for. Reviews that are close together in the 10D space end up in the same cluster.

Crucially, HDBSCAN marks reviews that don't fit any cluster as **noise** (label `-1`). We keep those separate rather than forcing them into a wrong cluster — that would corrupt our evidence.

**Result: 23 clusters found. 78% of substantive reviews captured. 22% marked as noise.**

Each cluster record looks like this:
```json
{
  "cluster_id": "c_13",
  "review_ids": ["rev_0063", "rev_0226", "rev_0316", ...],
  "size": 110,
  "tightness": 0.481
}
```

The `tightness` score measures how similar the reviews inside the cluster are to each other. Higher = more coherent = stronger evidence of one specific latent need.

---

## Stage 3 — Label (`src/label.py`) ✅ Done

We now have 23 anonymous clusters — groups of reviews that are mathematically similar. But we don't know yet what each group is *about*. This is the one place where we use AI.

### What we send to Claude

For each cluster, we pick up to 20 of the longest (most informative) reviews and send them to `claude-sonnet-4-6` with this task:

> "These reviews were grouped together by a clustering algorithm. What latent need do they share? Give me a `need` (one sentence), a `theme` (2–4 words), and a `summary` (one sentence about the evidence pattern). Return raw JSON only."

### What Claude returns

```json
{
  "need": "Users need smooth, clear, and properly synchronized audio playback across all games without lag or distortion.",
  "theme": "Audio quality issues",
  "summary": "Multiple users report sound lag, audio cutouts, and poor synchronization that break gameplay immersion."
}
```

### What Claude does NOT do

Claude does not decide which clusters are important. It does not rank them. It does not assign confidence scores. It does not say whether the roadmap addresses this need. It only names what it sees in the reviews. Everything else is handled by code.

### Caching

Every Claude response is saved to `data/label_cache/c_XX.json`. Re-running the pipeline makes zero API calls if all clusters are already cached. Pass `--refresh` to force re-labeling.

### The 23 labeled clusters

After Stage 3, every cluster has a name:

| Theme | Reviews | What users need |
|---|---|---|
| Game compatibility inconsistency | 232 | Games to work reliably regardless of device or update |
| Game acquisition guidance | 224 | A clear way to find and load game files |
| Game file acquisition | 207 | Guidance on obtaining and using game ROMs/ISOs |
| PSP emulator performance | 175 | Smooth, fast emulation without slowdowns |
| Game compatibility reliability | 170 | Wide game support with consistent performance |
| Game crash stability | 124 | Emulator to run games without crashing |
| Audio quality issues | 110 | Properly synchronized audio without lag |
| Game performance lag | 106 | Full-speed gameplay without frame drops |
| Black screen rendering | 94 | Games to display correctly without blank screens |
| WWE game compatibility | 94 | WWE games to run completely and smoothly |
| Multi-touch button input | 38 | Ability to press multiple buttons simultaneously |
| PS2 emulator request | 38 | Support for PS2 games, not just PSP |
| RAR extraction confusion | 39 | Built-in help for handling compressed game files |

---

## Stage 4 — Match (`src/match.py`) ✅ Done

Now we have 23 named needs. The question is: does the PPSSPP roadmap address any of them?

### How matching works

We embed each need's text (theme + need sentence) with the same `all-MiniLM-L6-v2` model, then compute cosine similarity against all 4,004 issue embeddings. For each need we take the top-5 most similar issues.

This is pure math — no LLM reading 4,004 issues one by one.

### Milestone awareness

We also loaded the 70 milestones and checked their state (open or closed). This matters:
- **Open milestone** (Future, v1.21, v1.22) → team is actively planning this
- **Closed milestone** → team already shipped a fix for this issue

If users are still complaining about something the team shipped in a closed milestone, that is the strongest signal of **MISUNDERSTOOD** — the team fixed the wrong thing.

Example: Issue #15469 ("Black screen on Raspberry Pi 3B") was closed in milestone `v1.14.0`. The fix shipped. But Android users are STILL reporting black screens. The team fixed a specific device edge case, not the general problem users experience.

### Verdict rules (code, not LLM)

| Situation | Verdict |
|---|---|
| Best similarity < 0.35 — nothing close on the roadmap | **IGNORED** |
| A matched issue was in a closed milestone (shipped fix, still complained about) | **MISUNDERSTOOD** |
| Related issues exist but none are actively being worked on | **UNDER-PRIORITIZED** |
| Active open issues exist — LLM judges if it addresses the real need | **MISUNDERSTOOD** or **addressed** |

The LLM is only called for the last case (ambiguous). All other verdicts come from rules in code.

### Results

| Verdict | Count |
|---|---|
| IGNORED | 1 |
| UNDER-PRIORITIZED | 7 |
| MISUNDERSTOOD | 15 |

---

## Stage 5 — Score (`src/score.py`) ✅ Done

Every gap gets a confidence score from an explicit formula. The AI never touches this number.

### The formula

```
confidence = (0.35 × volume_score) + (0.20 × tightness) + (0.45 × gap_clarity)
```

**Volume score** — log-scaled review count, normalized to [0, 1].
We use log so that 500 reviews beats 50 meaningfully, but doesn't dominate the formula 10×. Doubling reviews gives diminishing returns.

**Tightness** — the mean cosine similarity within the cluster from Stage 2.
Tighter cluster = reviews all circle the same specific problem = stronger evidence.

**Gap clarity** — derived from the verdict:
- IGNORED = 1.00 (clearest gap — nothing on roadmap)
- UNDER-PRIORITIZED = 0.80 (roadmap knows but deprioritized)
- MISUNDERSTOOD = 0.60 (roadmap has something but wrong angle)

**Why these weights?** Gap clarity (0.45) is most important — a clear roadmap gap matters most. Volume (0.35) is second — raw user demand is strong signal. Tightness (0.20) is third — a loose cluster with 200 reviews still counts.

### Merging duplicate clusters

Two sets of clusters turned out to represent the same underlying need:
- `c_18` + `c_06` → both about not knowing how to get game files → merged into "Game acquisition guidance" (309 reviews combined)
- `c_09` + `c_20` + `c_22` → all facets of "games run poorly" → merged into one entry (513 reviews combined)

Review IDs are unioned, tightness is weighted-averaged, confidence is recomputed on the merged pool.

### Final confidence scores

| Gap | Confidence | Formula |
|---|---|---|
| Games run poorly | **81.4%** | (0.35×1.00) + (0.20×0.52) + (0.45×0.80) |
| Game acquisition guidance | **77.3%** | (0.35×0.92) + (0.20×0.46) + (0.45×0.80) |
| Game compatibility reliability | **73.4%** | (0.35×0.94) + (0.20×0.67) + (0.45×0.60) |
| Device compatibility issues | **73.3%** | (0.35×0.84) + (0.20×0.49) + (0.45×0.80) |
| Game file acquisition | **71.4%** | (0.35×0.96) + (0.20×0.51) + (0.45×0.60) |

Every number is reproducible. A judge can recalculate any score by hand using the inputs stored in `gaps.json`.

---

## Stage 6 — Pipeline + Output ✅ Done

### `make run`

Running `make run` executes all 5 stages in order via `src/pipeline.py`. With caches warm, the full pipeline completes in **~27 seconds**. With `make refresh`, it recomputes everything from scratch.

### `gaps.json`

The final output. Contains:
- `headline_gaps` — the top 5 distinct unmet needs
- `all_gaps` — all 19 ranked gaps
- Full evidence trace per gap: review IDs + matched GitHub issue numbers
- Confidence breakdown per gap: every input value + the formula string
- Sample review texts (5 per gap) for quick human verification

### `make viewer`

Starts a local web server at `http://localhost:8000/viewer/`. The viewer reads `gaps.json` and shows each gap with its confidence bar, signal breakdown, verdict badge, sample review texts, and clickable GitHub issue links.

---

## Files and What They Contain

| File | Status | Contents |
|---|---|---|
| `src/ingest.py` | ✅ Done | Pulls reviews + GitHub data, caches locally |
| `src/cluster.py` | ✅ Done | Embeds, reduces, clusters — 23 clusters found |
| `src/label.py` | ✅ Done | Labels all 23 clusters via Claude API |
| `src/match.py` | ✅ Done | Cosine similarity match + milestone-aware verdicts |
| `src/score.py` | ✅ Done | Confidence formula + cluster merging + ranking |
| `src/pipeline.py` | ✅ Done | Orchestrates all stages → gaps.json |
| `data/reviews.json` | ✅ | 9,771 PPSSPP reviews with stable IDs |
| `data/embeddings.npy` | ✅ | 9,771 × 384 embedding vectors (cached) |
| `data/clusters.json` | ✅ | 23 clusters with review IDs and tightness |
| `data/labeled_clusters.json` | ✅ | 23 clusters with need / theme / summary added |
| `data/label_cache/` | ✅ | Per-cluster Claude responses (23 JSON files) |
| `data/issues.json` | ✅ | 4,004 real GitHub issues |
| `data/issue_embeddings.npy` | ✅ | 4,004 × 384 issue vectors (cached) |
| `data/milestones.json` | ✅ | 70 GitHub milestones (4 open, 66 closed) |
| `data/matched_needs.json` | ✅ | 23 needs with verdicts + matched issue numbers |
| `data/match_cache/` | ✅ | Per-cluster LLM verdict responses (cached) |
| `gaps.json` | ✅ | Final output — 5 headline gaps + 19 total ranked |
| `viewer/index.html` | ✅ | Browser UI — serve with `make viewer` |
| `DEFENSE.md` | ✅ | Live defense cheat sheet for judges |
