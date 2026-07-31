# Live Defense Cheat Sheet

Quick answers to the questions judges will ask. Numbers are from the actual output — use them exactly.

---

## "Walk me through what you built."

We built a 5-stage pipeline:
1. **Ingest** — 9,771 PPSSPP reviews + 4,004 GitHub issues + 70 milestones
2. **Cluster** — embed reviews locally (all-MiniLM-L6-v2), compress with UMAP, cluster with HDBSCAN → 23 clusters
3. **Label** — Claude reads a sample of each cluster and names the latent need (one sentence)
4. **Match** — cosine similarity between need embeddings and issue embeddings → top-5 issues per need → rule-based verdict (IGNORED / UNDER-PRIORITIZED / MISUNDERSTOOD)
5. **Score** — explicit formula: 35% volume + 20% tightness + 45% gap clarity → confidence %

The LLM only names clusters and resolves ambiguous verdicts. It never decides rankings or confidence numbers. Those are code.

---

## "Why is gap #1 ranked #1?"

**Gap #1: "Games run poorly (performance & compatibility)" — 81.4% confidence**

Three clusters were merged because they describe the same root need:
- c_09: 232 reviews about game compatibility breaking unpredictably
- c_20: 175 reviews about general emulator slowness
- c_22: 106 reviews about frame-rate lag

**Total: 513 reviews** — the largest pool of evidence in our dataset.

The roadmap (issue #14349, #15281, #14074) acknowledges these problems but all matched issues are **closed with no active milestone** — the team knows about this but isn't actively working on it. That's UNDER-PRIORITIZED.

Formula: `(0.35 × 1.00) + (0.20 × 0.52) + (0.45 × 0.80) = 81.4%`
- Volume = 1.00 (513 reviews = top of the log scale)
- Tightness = 0.52 (weighted average across the 3 clusters)
- Gap clarity = 0.80 (UNDER-PRIORITIZED)

---

## "Why 81.4% and not 90%?"

The tightness score pulls it down. Tightness = mean cosine similarity within the cluster = 0.52. This cluster is somewhat loose — reviews talk about different games and different devices, so they're not pointing at one single identical problem. A tighter cluster (e.g., audio lag at 0.48) would score higher on tightness but is smaller.

The formula is honest: high volume + clear roadmap gap ≠ automatically 90%. The 0.20 tightness weight penalizes loose evidence.

---

## "Why is gap #3 MISUNDERSTOOD and not UNDER-PRIORITIZED?"

**Gap #3: "Game compatibility reliability" — 73.4% confidence, MISUNDERSTOOD**

The roadmap has issue #18761 ("Feature Request: System Support") which is an active, open issue. Because an active issue exists, we used Claude to decide: does this issue address the same need users have?

Claude's verdict: MISUNDERSTOOD — the roadmap issue is about a generic system support request, while users need reliable gameplay across a wide range of specific games. The roadmap is working on infrastructure; users need game-by-game fixes.

---

## "Defend the black screen verdict."

**Gap #5: "Black screen rendering" — 72.9%, UNDER-PRIORITIZED**

Issue #15469 ("Black screen on Raspberry Pi 3B") was closed in milestone `v1.14.0` — the team shipped a fix. But PPSSPP Android users are *still* reporting black screens. Our verdict: **MISUNDERSTOOD** — the team fixed a specific Raspberry Pi edge case, not the general Android rendering failure users experience.

This is the most concrete example of the gap between what the team thinks they fixed and what users actually need.

---

## "Isn't 'games run poorly' just a complaint? How is that a latent need?"

Good challenge. Here's the distinction:

**Complaint** (what anyone can see): "Users often mention lag" — you get this from counting keywords.

**Latent need** (what we surface): Users are saying dozens of different things — "GTA runs at 15fps," "god of war crashes on my samsung," "too slow on my phone," "new update broke performance." No single user said "I need better CPU optimization for mid-range Android devices."

Our **clustering** found that these reviews are mathematically close in embedding space — they're all circling the same underlying problem even though the surface text is completely different. The cluster *proves* the pattern exists without anyone having to state it directly. That's the latent part.

---

## "Here's a gap you missed — why?"

If a judge points out a gap:

1. **Check if it's in our full ranked list** (19 gaps total, not just the top 5). It might be ranked #8 or #12.
2. **If it's truly missing**: It's probably in the 22% noise we dropped. HDBSCAN marks reviews that don't fit a strong cluster as noise. If a real need is scattered and incoherent in review text, our clustering won't surface it — that's an honest limitation of density-based clustering.
3. **Honest answer**: "Our method finds patterns that exist across many reviews. A need mentioned in fewer than ~30 reviews won't form a cluster. That's a deliberate tradeoff — we prioritize evidence strength over coverage."

---

## "Why PPSSPP?"

- 9,771 reviews in the dataset — one of the largest sets for any open-source F-Droid app
- Active GitHub: 4,004 real issues + 70 milestones — rich roadmap to compare against
- Complex tension: passionate users want broad game compatibility and smooth performance; a small open-source team has limited bandwidth. That tension is exactly where unmet needs live.
- Alternative (Wikipedia Android) was dropped because it uses Phabricator for issues — GitHub shows only PRs, zero real issues.

---

## "How does your confidence formula work? Can you justify the weights?"

Formula: `confidence = (0.35 × volume) + (0.20 × tightness) + (0.45 × gap_clarity)`

- **Gap clarity (0.45)** — the most important question is: does the roadmap actually miss this? IGNORED=1.0, UNDER-PRIORITIZED=0.80, MISUNDERSTOOD=0.60. Highest weight because a weak gap signal with lots of reviews is less important than a strong gap signal with moderate reviews.
- **Volume (0.35)** — raw user demand matters a lot. Log-scaled so 500 reviews vs 50 reviews doesn't give 10× weight — doubling reviews gives diminishing returns.
- **Tightness (0.20)** — coherence of the evidence. A tight cluster (all reviews saying the same thing) is stronger evidence than a loose one. Lower weight because even loose clusters with 200 reviews are meaningful.

Weights are tunable constants at the top of score.py — change them and re-run in seconds.

---

## "Why do 90%-sure and 55%-sure gaps differ in your system?"

Our range: **81.4% (top) to 57.3% (bottom)** — a 24-point spread.

The bottom gap (Multi-touch button input, 57.3%) is lower because:
- Only 38 reviews (small volume) → low volume score
- Tightness 0.34 (loosest cluster) → low tightness
- MISUNDERSTOOD verdict → gap clarity 0.60 (not the strongest gap signal)

Formula: `(0.35 × 0.67) + (0.20 × 0.34) + (0.45 × 0.60) = 57.3%`

The top gap gets 81.4% because it has maximum volume (1.0), decent tightness (0.52), and a clear UNDER-PRIORITIZED signal (0.80). Every digit is explained by the formula.

---

## Quick numbers to have ready

| Gap | Confidence | Reviews | Verdict | Key issue |
|---|---|---|---|---|
| Games run poorly | 81.4% | 513 | UNDER-PRIORITIZED | #14349, #15281, #14074 (closed, no milestone) |
| Game acquisition guidance | 77.3% | 309 | UNDER-PRIORITIZED | #15462 (closed, no milestone) |
| Game compatibility reliability | 73.4% | 170 | MISUNDERSTOOD | #18761 (open, wrong angle) |
| Device compatibility issues | 73.3% | 70 | UNDER-PRIORITIZED | #18264 (open, no milestone) |
| Black screen rendering | 72.9% | 94 | MISUNDERSTOOD | #15469 (shipped in v1.14.0 but users still report it) |

**Total reviews analyzed:** 9,771  
**Clusters found:** 23  
**After noise filtering:** 2,905 substantive reviews  
**GitHub issues checked:** 4,004  
**Open milestones:** 4 (Future, Future-Prio, v1.21, v1.22)
