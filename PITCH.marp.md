---
marp: true
theme: default
paginate: true
size: 16:9
title: Silent Stakeholder
style: |
  section { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  h1 { color: #111; }
  strong { color: #1d4ed8; }
  blockquote { border-left: 4px solid #f59e0b; background: #fffbeb; padding: 0.5em 1em; }
---

# Silent Stakeholder
## Find unmet user needs the roadmap is missing

**PPSSPP** · `org.ppsspp.ppsspp` · `hrydgard/ppsspp`

9,771 reviews · 4,004 issues · Top 5 latent gaps

> Not a complaint summarizer — traceable pipeline with evidence IDs

---

# The problem
## Users and teams never sync

- **Users:** 9,771 reviews — noisy, honest, ignored
- **Team:** 4,004 GitHub issues + 70 milestones

**Silent stakeholders** — affected by every decision, no voice in planning

> Reviews are the signal. GitHub is the roadmap. Nobody connects them systematically.

---

# What we build
## Every gap has four things

1. **The need** — latent, in plain language
2. **Confidence** — from formula (not AI opinion)
3. **Evidence** — `rev_XXXX` + GitHub `#NNNN`
4. **Verdict** — IGNORED · UNDER-PRIORITIZED · MISUNDERSTOOD

Ranked strongest first · No evidence → no gap

---

# How to start

```bash
pip install -r requirements.txt   # once
make run      # → gaps.json
make qa       # optional QA grades
make viewer   # → localhost:8000/viewer/
```

Viewer is **read-only** — no AI runs at demo time

---

# End-to-end flow

```
Reviews + GitHub → Ingest → Cluster → Label → Match → Score → gaps.json → Viewer
                                                      ↘ QA critic (optional)
```

- **Code:** cluster, match rules, score, rank
- **Claude:** label, ambiguous verdicts, QA lint

---

# Five stages

| Stage | AI? | Output |
|-------|-----|--------|
| Ingest | No | reviews.json, issues.json |
| Cluster | No | 23 clusters |
| Label | Yes | latent need text |
| Match | Sometimes | verdict |
| Score | No | gaps.json ranked |

---

# Clustering
## Finding latent patterns

Embed → filter → UMAP → HDBSCAN → 23 clusters

**Different complaints → same cluster:**
- "GTA lags" · "God of War crashes" · "too slow"

→ **Gap #1:** predictable performance across game×device

Cluster membership = ground truth. LLM only names groups.

---

# Three Claude agents

| Agent | Role |
|-------|------|
| **Label** | Name each cluster |
| **Match** | Ambiguous verdicts only |
| **QA critic** | pass/warn/fail — read-only |

Same API key · cached · never picks rank or confidence

---

# Confidence formula

```
confidence = 0.35×volume + 0.20×tightness + 0.45×gap_clarity
```

**Gap #1:** `(0.35×0.9991) + (0.20×0.5189) + (0.45×0.80) = 81.3%`

513 reviews · UNDER-PRIORITIZED · recalculable from gaps.json

---

# Verdicts

| Verdict | Meaning |
|---------|---------|
| IGNORED | No roadmap match |
| UNDER-PRIORITIZED | Known but not actively worked |
| MISUNDERSTOOD | Wrong fix or wrong angle |

**Example:** Black screen #10 — Pi fix shipped, Android users still complain

---

# Top 5 results

| # | Gap | Conf | Verdict |
|---|-----|------|---------|
| 1 | Games run poorly | 81.3% | UNDER-PRIORITIZED |
| 2 | Game acquisition | 80.5% | UNDER-PRIORITIZED |
| 3 | Compatibility | 73.4% | MISUNDERSTOOD |
| 4 | Device compat | 73.3% | UNDER-PRIORITIZED |
| 5 | Emulation speed | 71.3% | UNDER-PRIORITIZED |

18 total gaps · evidence in gaps.json

---

# Latent need vs summary

❌ "513 users said lag"

✅ "Users need consistent performance across all titles regardless of device specs"

Different surface complaints → one hidden need → 513 review IDs as proof

---

# Live demo

1. Open **Results page** (make viewer)
2. Gap #1 → need + formula + 81.3%
3. Expand **evidence** → rev IDs + issue #15281
4. Show **QA grades**

http://localhost:8000/viewer/

---

# Summary

- Latent needs from clustering — not keyword counts
- Evidence-first — every gap traceable
- Code scores · Claude assists
- Three agents: Label · Match · QA critic

```bash
make run → make qa → make viewer
```

**Ask me to defend any number — I'll show score.py and the IDs.**
