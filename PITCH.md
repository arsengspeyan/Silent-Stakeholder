# Silent Stakeholder — Pitch Deck

> **Format:** Markdown slide deck (14 slides)  
> **Convert to PDF/PPT:** [Marp](https://marp.app/) · paste into Google Slides · export from Notion  
> **Live demo:** run `make viewer` → http://localhost:8000/viewer/

---

## Slide 1 — Title

### Silent Stakeholder

**Find unmet user needs the roadmap is missing**

- **App:** PPSSPP · `org.ppsspp.ppsspp`
- **GitHub:** `hrydgard/ppsspp`
- **Input:** 9,771 reviews + 4,004 issues + 70 milestones
- **Output:** Top 5 ranked latent needs with evidence + verdicts

> Not a complaint summarizer. A traceable pipeline that infers hidden needs and diffs them against the roadmap.

---

## Slide 2 — Problem

### Users and teams never sync

**Users (silent stakeholders)**
- 9,771 app store reviews
- Honest, messy, unfiltered
- No seat in sprint planning

**Team (roadmap)**
- 4,004 GitHub issues
- 70 milestones
- Planned work — may miss real user needs

> The gap between what users need and what the team builds is invisible without a system to connect both sides.

---

## Slide 3 — What we build

### Every gap has four things

| # | Field | Meaning |
|---|--------|---------|
| 1 | **The need** | Latent user need in plain language |
| 2 | **Confidence** | Calibrated score from a fixed formula |
| 3 | **Evidence** | `rev_XXXX` review IDs + GitHub `#NNNN` issues |
| 4 | **Verdict** | IGNORED · UNDER-PRIORITIZED · MISUNDERSTOOD |

Ranked by evidence strength. Strongest first. **No evidence → no gap.**

---

## Slide 4 — How to start

### Run the app in four steps

1. **Setup (once)**  
   `cp .env.example .env` → add `ANTHROPIC_API_KEY` + `GITHUB_TOKEN`  
   `pip install -r requirements.txt`

2. **Build the report**  
   `make run` → writes `gaps.json`

3. **QA check (optional)**  
   `make qa` → pass/warn/fail grades (does not change scores)

4. **Open the UI**  
   `make viewer` → http://localhost:8000/viewer/

```bash
make run
make qa
make viewer
# Viewer only reads JSON — no AI at demo time
```

---

## Slide 5 — End-to-end flow

### From raw data to ranked gaps

```
Reviews (HuggingFace)  ──┐
                         ├──► INGEST ──► CLUSTER ──► LABEL ──► MATCH ──► SCORE ──► gaps.json
GitHub (issues)        ──┘                                                      │
                                                                                 ├──► Viewer
                                                                                 └──► QA critic (optional)
```

**Yellow = Claude agents** · **Green = output** · **Blue = code/math**

---

## Slide 6 — Five stages

| Stage | Script | Does | AI? |
|-------|--------|------|-----|
| 1 Ingest | `ingest.py` | Download data, assign stable IDs | No |
| 2 Cluster | `cluster.py` | Embed + UMAP + HDBSCAN → 23 clusters | No |
| 3 Label | `label.py` | Name each cluster as a latent need | Label agent |
| 4 Match | `match.py` | Compare need vs issues → verdict | Edge cases |
| 5 Score | `score.py` | Formula + merge + rank | No |
| QA | `qa_gaps.py` | Lint output pass/warn/fail | QA critic |

**Code decides:** grouping · confidence · ranking · most verdicts  
**Claude assists:** naming · ambiguous verdicts · QA validation

---

## Slide 7 — Clustering

### Finding patterns — not summarizing

1. **Embed** — sentence-transformers locally (384-dim)
2. **Filter** — drop reviews < 50 chars ("Good", "Nice")
3. **UMAP** — 384 → 10 dimensions
4. **HDBSCAN** — auto cluster count; noise excluded
5. **Result** — 23 clusters with `review_ids` + tightness

**Example:**  
"GTA lags" · "God of War crashes" · "too slow after update"  
→ cluster c_09 → merged into **Gap #1**

> Cluster membership is ground truth. The LLM never moves reviews between groups.

---

## Slide 8 — Three Claude agents

| Agent | Script | Job |
|-------|--------|-----|
| **Label** | `label.py` | Names each cluster from ~20 sample reviews |
| **Match** | `match.py` | Ambiguous verdicts only (MISUNDERSTOOD vs addressed) |
| **QA critic** | `qa_gaps.py` | Grades latent need vs complaint summary — read-only |

All use **Anthropic** `claude-sonnet-4-6` · same API key · cached to disk.

> Math finds patterns. Claude names and validates. Code scores and ranks.

---

## Slide 9 — Confidence formula

### Every percentage comes from code

```
confidence = (0.35 × volume) + (0.20 × tightness) + (0.45 × gap_clarity)
```

| Signal | Weight | Meaning |
|--------|--------|---------|
| Volume | 35% | Log-scaled review count |
| Tightness | 20% | Similarity within cluster |
| Gap clarity | 45% | How clearly roadmap misses the need |

**Gap clarity values:** IGNORED = 1.0 · UNDER-PRIORITIZED = 0.8 · MISUNDERSTOOD = 0.6

**Gap #1 example:**
```
(0.35 × 0.9991) + (0.20 × 0.5189) + (0.45 × 0.80) = 0.8135 → 81.3%
513 reviews · UNDER-PRIORITIZED
```

---

## Slide 10 — Verdicts

| Verdict | Meaning |
|---------|---------|
| **IGNORED** | No similar GitHub issue (similarity < 0.35) |
| **UNDER-PRIORITIZED** | Issues exist but closed, stale, or not on open milestones |
| **MISUNDERSTOOD** | Team works on related problem — wrong angle; or shipped fix, users still complain |

**Example — Black screen (rank #10, 63.9%)**  
Issue #15469 shipped in v1.14.0 for Raspberry Pi. Android users still report black screens.  
→ Team fixed a narrow case, not the general rendering failure.

---

## Slide 11 — Results

### Top 5 unmet needs · PPSSPP

| # | Theme | Conf | Reviews | Verdict |
|---|-------|------|---------|---------|
| 1 | Games run poorly | 81.3% | 513 | UNDER-PRIORITIZED |
| 2 | Game acquisition guidance | 80.5% | 516 | UNDER-PRIORITIZED |
| 3 | Game compatibility reliability | 73.4% | 170 | MISUNDERSTOOD |
| 4 | Device compatibility | 73.3% | 70 | UNDER-PRIORITIZED |
| 5 | Emulation speed | 71.3% | 54 | UNDER-PRIORITIZED |

- **18 total** ranked gaps in `gaps.json`
- Gap #2 QA grade: **pass** (clearest latent need)
- Gap #1: merged clusters c_09 + c_20 + c_22

---

## Slide 12 — Latent need example

### Not a complaint summary

| ❌ Summarizer | ✅ Silent Stakeholder |
|--------------|----------------------|
| "513 users complained about slow games" | "Users need consistent performance across all PSP titles regardless of game size, graphics type, or device specs" |

**Surface complaints (different words):**
- GTA lags on certain titles
- 2D games lag while 3D run fine
- Specific games crash mid-mission
- Android slower than PC/Linux

**Hidden need:** Predictable playability per game×device — users never wrote that sentence.

**Proof:** 513 `review_ids` · merge_reason in `score.py` · issues #15281, #14074

---

## Slide 13 — Live demo

### Demo script (~2 minutes)

1. **Before demo:** `make run` · `make qa` · `make viewer` (pipeline already done)
2. **Results page:** stats + pipeline strip
3. **Gap #1:** need sentence → formula bars → 81.3%
4. **Evidence:** expand → sample reviews + rev IDs + issue #15281
5. **QA banner:** pass/warn/fail from QA critic
6. **Defend rank:** #1 beats #2 on tightness — formula in `score.py`, not AI

→ http://localhost:8000/viewer/

---

## Slide 14 — Summary

### Silent Stakeholder

- **Latent needs** — clustering finds patterns users never stated in one sentence
- **Evidence-first** — every gap has review IDs + issue IDs
- **Auditable scores** — formula in code, not LLM opinion
- **Roadmap verdicts** — IGNORED / UNDER-PRIORITIZED / MISUNDERSTOOD
- **Three Claude agents** — Label · Match · QA critic (optional)

```bash
make run  →  make qa  →  make viewer
```

> Ask me why any number is what it is — I'll point to `score.py` and the IDs in `gaps.json`.

---

## Speaker notes (optional)

**If asked "Why not just summarize complaints?"**  
→ Show Slide 12 + open evidence on Gap #1 in the viewer.

**If asked "Why rank #1?"**  
→ 513 reviews, merged clusters, UNDER-PRIORITIZED, formula = 81.3%, beats #2 on tightness.

**If asked "What does AI do?"**  
→ Slide 8. Three agents. Never grouping, never scores, never rank.

**If asked "Gap you missed?"**  
→ Check full list of 18. Multi-touch is #18 at 57.3%. Noise reviews never cluster.
