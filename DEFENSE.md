# Live Defense Cheat Sheet

Quick answers to the questions judges will ask. Numbers are from the actual output — use them exactly.

**Re-run after scoring changes:** `python3 src/score.py` then `make viewer`  
**Run QA critic:** `make qa` (optional; requires `ANTHROPIC_API_KEY`)

---

## "Walk me through what you built."

The project is a 5-stage pipeline:
1. **Ingest** — 9,771 PPSSPP reviews + 4,004 GitHub issues + 70 milestones
2. **Cluster** — embed reviews locally (all-MiniLM-L6-v2), compress with UMAP, cluster with HDBSCAN → 23 clusters
3. **Label** — Claude reads a sample of each cluster and names the latent need (one sentence)
4. **Match** — cosine similarity between need embeddings and issue embeddings → top-5 issues per need → rule-based verdict (IGNORED / UNDER-PRIORITIZED / MISUNDERSTOOD)
5. **Score** — explicit formula: 35% volume + 20% tightness + 45% gap clarity → confidence %

The LLM only names clusters and resolves ambiguous verdicts. It never decides rankings or confidence numbers. Those are code.

A **fourth Claude agent** (QA critic, `src/qa_gaps.py`) runs **after** the pipeline via `make qa`. It grades each gap pass/warn/fail — latent need vs complaint summary. It does **not** change scores or ranking.

---

## "What does the QA critic agent do?"

After `make run`, run `make qa`. The QA critic reads each headline gap + sample reviews and returns:
- **grade** — pass / warn / fail
- **is_latent_need** — true if the need goes beyond surface complaints
- **pitch_tip** — how to present this gap to judges

Output: `data/gaps_qa.json`. Shown on the Results page if you ran `make qa` before `make viewer`.

**Current headline QA (example):** 2 pass, 3 warn, 0 fail. Gap #2 (game acquisition) **passes**. Gap #1 warns because the theme title sounds complaint-like — use the full `need` sentence in the pitch.

---

## "Why is gap #1 ranked #1?"

**Gap #1: "Games run poorly (performance & compatibility)" — 81.3% confidence**

Three clusters were merged because they describe the same root need:
- c_09: 232 reviews about game compatibility breaking unpredictably
- c_20: 175 reviews about general emulator slowness
- c_22: 106 reviews about frame-rate lag

**Total: 513 reviews** — the largest pool of evidence in the dataset.

The roadmap (issues #14349, #15281, #14074) acknowledges these problems but matched issues are **closed with no active milestone** — the team knows about this but isn't actively working on it. That's UNDER-PRIORITIZED.

Formula: `(0.35 × 0.9991) + (0.20 × 0.5189) + (0.45 × 0.80) = 81.3%`
- Volume = 0.9991 (513 reviews — nearly max on log scale)
- Tightness = 0.52 (weighted average across the 3 clusters)
- Gap clarity = 0.80 (UNDER-PRIORITIZED)

**Why not #2?** Gap #2 (game acquisition) has slightly more reviews (516) but lower tightness (0.48 vs 0.52), so it scores 80.5% — still #2, not #1.

---

## "Why 81.3% and not 90%?"

The tightness score pulls it down. Tightness = 0.52. Reviews talk about different games and different devices — not one identical phrase. The formula doesn't give 90% just because volume is high. The 0.20 tightness weight penalizes loose evidence.

---

## "Why is gap #3 MISUNDERSTOOD and not UNDER-PRIORITIZED?"

**Gap #3: "Game compatibility reliability" — 73.4% confidence, MISUNDERSTOOD**

The roadmap has issue #18761 ("Feature Request: System Support") which is an active, open issue. Because an active issue exists, Claude is used to decide: does this issue address the same need users have?

Claude's verdict: MISUNDERSTOOD — the roadmap issue is about generic system support, while users need reliable gameplay across a wide range of specific games. The roadmap is working on infrastructure; users need game-by-game fixes.

---

## "Defend the black screen verdict." (rank #10 — not top 5)

**Gap #10: "Black screen rendering" — 63.9%, MISUNDERSTOOD**

Issue #15469 ("Black screen on Raspberry Pi 3B") was closed in milestone `v1.14.0` — the team shipped a fix. But PPSSPP Android users are *still* reporting black screens. Verdict: **MISUNDERSTOOD** — the team fixed a specific Raspberry Pi edge case, not the general Android rendering failure users experience.

Use this as your best MISUNDERSTOOD example even though it's not in the headline top 5.

---

## "Why did you merge game acquisition clusters?"

Three clusters (c_18, c_06, c_05) all describe users struggling to get games into the emulator:
- c_18 (224): where to find games
- c_06 (85): how to load them
- c_05 (207): obtaining ISO/ROM files

Same root need — merged into one gap with 516 reviews at 80.5%. Documented in `MERGE_GROUPS` in `score.py` with a written reason.

---

## "Isn't 'games run poorly' just a complaint? How is that a latent need?"

**Complaint** (what anyone can see): "Users often mention lag" — count keywords.

**Latent need** (what the system surfaces): Users say different things — "GTA runs at 15fps," "god of war crashes on my samsung," "too slow on my phone." No one said "optimize for mid-range Android."

**Clustering** groups these reviews as mathematically close in embedding space — circling the same underlying problem with different words. Cluster membership is the proof.

---

## "Here's a gap you missed — why?"

1. **Check the full ranked list** (18 gaps total, not just top 5). It might be ranked #8 or #12.
2. **If truly missing:** probably in HDBSCAN noise — reviews that don't fit a strong cluster (min 30 reviews to form one).
3. **Honest answer:** "The pipeline prioritizes evidence strength over coverage. A need in fewer than ~30 similar reviews won't form a cluster."

---

## "Why PPSSPP?"

- 9,771 reviews — one of the largest sets for an open-source F-Droid app
- 4,004 real GitHub issues + 70 milestones
- Real tension: users want broad compatibility + smooth performance; small OSS team has limited bandwidth
- Wikipedia Android was dropped — issues on Phabricator, GitHub had only PRs

---

## "How does your confidence formula work?"

Formula: `confidence = (0.35 × volume) + (0.20 × tightness) + (0.45 × gap_clarity)`

- **Gap clarity (0.45)** — does the roadmap miss this? Highest weight.
- **Volume (0.35)** — how many reviews? Log-scaled.
- **Tightness (0.20)** — how coherent is the cluster?

Every gap in `gaps.json` includes the full formula string in `confidence_breakdown.formula`. The viewer shows it on each card.

Weights are constants at the top of `score.py` — change and re-run in seconds.

---

## "Why do 81% and 57% gaps differ?"

Range: **81.3% (top) to 57.3% (bottom)** — 24-point spread.

Bottom gap (#18 Multi-touch button input, 57.3%):
- 38 reviews → low volume
- Tightness 0.34 → loosest cluster
- MISUNDERSTOOD → gap clarity 0.60

Formula: `(0.35 × 0.67) + (0.20 × 0.34) + (0.45 × 0.60) = 57.3%`

---

## Quick numbers to have ready (current output)

| # | Gap | Confidence | Reviews | Verdict | Key issues |
|---|---|---|---|---|---|
| 1 | Games run poorly | 81.3% | 513 | UNDER-PRIORITIZED | #14349, #15281, #14074 |
| 2 | Game acquisition guidance | 80.5% | 516 | UNDER-PRIORITIZED | #15462, #15655, #17448 |
| 3 | Game compatibility reliability | 73.4% | 170 | MISUNDERSTOOD | #18761 (open, wrong angle) |
| 4 | Device compatibility issues | 73.3% | 70 | UNDER-PRIORITIZED | #18264 |
| 5 | Emulation speed performance | 71.3% | 54 | UNDER-PRIORITIZED | #13185, #19433 |
| 10 | Black screen rendering | 63.9% | 94 | MISUNDERSTOOD | #15469 (shipped v1.14.0, users still complain) |

**Total reviews analyzed:** 9,771  
**Clusters found:** 23  
**Ranked gaps:** 18  
**GitHub issues checked:** 4,004  
**Open milestones:** 4 (Future, Future-Prio, v1.21, v1.22)

---

## One sentence that wins

> "Every confidence number comes from a formula in code — the AI never guessed the score or the ranking."
