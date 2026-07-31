# CLAUDE.md — Silent Stakeholder (Hackathon)

## What we're building
A pipeline that finds UNMET user needs a product's roadmap is missing.
Two sides of ONE app:
- USER side: reviews from the `sealuzh/app_reviews` HuggingFace dataset
- ROADMAP side: GitHub issues + milestones (via api.github.com)
Output: top 3–5 latent needs, each with confidence, evidence (IDs), and a verdict.

## Chosen app
<!-- fill in once confirmed, e.g. AntennaPod / de.danoeh.antennapod / github AntennaPod/AntennaPod -->
App: TBD
Package name: TBD
GitHub repo: TBD

## The core principle (do not violate)
This is NOT a complaint summarizer. We infer LATENT needs — patterns across
many reviews that users never stated directly. Listing frequent complaints = fail.

Every gap MUST have:
1. need (plain language)
2. confidence score (from a FORMULA, never from the LLM's opinion)
3. evidence trace (specific review IDs + roadmap issue IDs)
4. verdict: IGNORED | UNDER-PRIORITIZED | MISUNDERSTOOD

## Architecture (deterministic skeleton; LLM is a helper, not the brain)
1. Ingest reviews + GitHub issues, each with a stable ID
2. Embed reviews locally (sentence-transformers) and cluster them → candidate themes
3. LLM labels each cluster (names the latent need). Cluster membership = ground truth
4. Match each theme to GitHub issues → assign verdict from issue label/status
5. Confidence via explicit formula (review count, cluster tightness, star severity, recency)
6. Emit ranked gaps.json, strongest evidence first

## Rules for the agent
- LLM (Anthropic API) is used ONLY for: labeling clusters, verdict reasoning, drafting need text.
- LLM NEVER decides the final ranking or the confidence numbers. Those are code.
- Embeddings are LOCAL (sentence-transformers), not an API.
- Cache every LLM call to disk (hash input → JSON), so re-runs are free and reproducible.
- Structured output: ask the model for JSON, strip code fences, try/except the parse.
- Secrets in env vars / .env (gitignored). Never commit keys.
- Every stage must be inspectable — I have to defend every output to judges.
- Prefer simple, readable code over clever abstractions. Explain non-obvious choices in comments.

## Conventions
- Python. Keep dependencies in requirements.txt.
- One runnable entrypoint: `make run` (or run.sh).
- IDs are the evidence currency — never drop them anywhere in the pipeline.
- Commit early and often with honest messages. No giant single commits.

## Repo layout (target)
```
data/           # cached raw + intermediate (gitignored except samples)
src/
  ingest.py     # pull reviews + github issues
  cluster.py    # embed + cluster reviews
  label.py      # LLM cluster labeling (cached)
  match.py      # theme -> roadmap matching + verdict
  score.py      # confidence formula
  pipeline.py   # runs all stages -> gaps.json
viewer/         # thin UI over gaps.json
gaps.json       # final output
README.md
```
