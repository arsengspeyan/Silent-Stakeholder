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

## What We Built in Part 1 & 2: The Ingest Stage

Before we can find gaps, we need data. Part 1 and 2 set up the project and pulled all the raw data.

### The Project Structure

We created a clean folder layout:

```
src/          ← all the Python code, one file per stage
data/         ← all cached data (not uploaded to GitHub)
viewer/       ← will become a simple UI to browse results
gaps.json     ← the final output (top 3–5 unmet needs)
```

Each stage of the pipeline is its own file:

| File | What it does |
|---|---|
| `ingest.py` | Pulls reviews + GitHub data |
| `cluster.py` | Groups similar reviews together |
| `label.py` | Uses AI to name each group |
| `match.py` | Compares groups to the roadmap |
| `score.py` | Calculates a confidence number |
| `pipeline.py` | Runs all stages in order |

### Side 1 — User Reviews (`data/reviews.json`)

We used a public dataset on HuggingFace called `sealuzh/app_reviews`. It contains Play Store reviews for hundreds of apps.

**What we did:**
1. Downloaded the full dataset (288,065 reviews total across all apps)
2. Filtered to only PPSSPP reviews → **9,771 reviews**
3. Sorted them by date + text so the order is always the same
4. Assigned each review a stable ID like `rev_0001`, `rev_0002`, etc.

**Why stable IDs matter:** Every review ID is our "evidence receipt." Later, when we say "users need better save sync," we can point to specific reviews like `rev_0342`, `rev_1891`, `rev_4420` that prove it. Judges can check.

Each review record looks like this:
```json
{
  "id": "rev_0001",
  "package_name": "org.ppsspp.ppsspp",
  "text": "Great emulator but save states keep getting corrupted...",
  "date": "2021-03-14",
  "stars": 3
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

Each issue record looks like this:
```json
{
  "id": 1823,
  "title": "Save states get corrupted on Android 12",
  "state": "open",
  "labels": ["bug", "Android"],
  "milestone": "v1.15",
  "created_at": "2022-06-01",
  "updated_at": "2023-01-15"
}
```

### Smart Caching

Every time you run the pipeline, it checks: "Do the data files already exist?" If yes, it skips the download and uses what is already saved. This means:

- First run: downloads everything (takes a minute or two)
- Every run after: instant, uses the local cache

If you want fresh data, you run: `python src/ingest.py --refresh`

We also handle **GitHub rate limits** gracefully. GitHub only allows a certain number of API requests per hour. If we hit the limit, the script prints a clear message and waits — instead of crashing with a confusing error.

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

## What Is Coming Next

### Part 3 — Clustering
We will take the 9,771 reviews and turn them into groups of similar reviews. Reviews that talk about the same underlying problem will land in the same cluster.

We do this locally on your computer using a library called `sentence-transformers`. It converts each review into a list of numbers (a "vector") that captures its meaning. Reviews with similar meanings will have similar numbers, so we can group them mathematically.

No AI API call is needed here. This is pure math.

### Part 4 — Labeling
We take each cluster of similar reviews and send a sample to Claude. Claude reads them and writes a one-sentence description of the latent need those users share. The result is cached so we only pay for this once.

### Part 5 — Matching
We compare each labeled need against the GitHub issues using the same vector math. If a need is already well-covered in the roadmap, it gets a low urgency score. If it is missing — that is a gap.

### Part 6 — Scoring & Output
We run the confidence formula on each gap and produce `gaps.json`: a ranked list of the top 3–5 unmet needs, each with the evidence that backs it up.

---

## Files Created

| File | Purpose |
|---|---|
| `src/ingest.py` | Stage 1: pulls and caches all raw data |
| `src/cluster.py` | Stage 2: placeholder, ready for implementation |
| `src/label.py` | Stage 3: placeholder, ready for implementation |
| `src/match.py` | Stage 4: placeholder, ready for implementation |
| `src/score.py` | Stage 5: placeholder, ready for implementation |
| `src/pipeline.py` | Orchestrator: placeholder, ready for implementation |
| `data/reviews.json` | 9,771 PPSSPP reviews with stable IDs |
| `data/issues.json` | 4,004 real GitHub issues |
| `data/milestones.json` | 70 GitHub milestones |
| `requirements.txt` | Python dependencies |
| `Makefile` | `make run` entrypoint |
| `.env.example` | Template for secrets |
| `.gitignore` | Keeps secrets and data off GitHub |
| `README.md` | Project overview |
| `CLAUDE.md` | Instructions for the AI assistant |
