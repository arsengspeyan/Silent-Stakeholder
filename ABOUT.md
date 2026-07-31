# Silent Stakeholder — What It Is and Why It Matters

## The Problem

Every app has two groups of people who shape its future:

**Group 1 — The team.** Developers, product managers, designers. They decide what gets built next. They track their plans on GitHub: issues, milestones, upcoming releases.

**Group 2 — The users.** Thousands of real people who use the app every day. They leave reviews on app stores. They say what frustrates them, what they wish existed, what made them switch to a competitor.

Here is the uncomfortable truth: **these two groups are almost never in sync.**

The team is busy shipping features. The users are busy leaving reviews that nobody on the team is systematically reading. The result? Products keep building things users don't care about, while the things users desperately need stay unbuilt — sometimes for years.

---

## Who Are the Silent Stakeholders?

The users.

They are stakeholders in the product — its success or failure directly affects their experience. But they have no seat at the table. Nobody asks them "what should we build next?" They only get to leave a star rating and a few sentences of text that disappear into a sea of thousands of other reviews.

They are **silent** not because they have nothing to say, but because nobody has built the bridge between what they say and what the team decides to build.

This project is that bridge.

---

## What We Built

Silent Stakeholder is a data pipeline that reads both sides — user reviews and the development roadmap — and finds the **gaps**: real user needs that the team is not addressing.

It does not just list complaints. Complaints are noise. We dig deeper.

We look for **latent needs**: patterns hiding across hundreds of reviews where users are all circling around the same underlying problem, even if they each describe it differently. We surface those patterns, match them against the roadmap, and produce a ranked list of unmet needs — each one backed by real evidence.

The output is a file called `gaps.json`. It contains the top 3 to 5 unmet needs, each with:

- A plain-language description of the need
- A confidence score calculated by a formula (not guessed by AI)
- A list of specific review IDs that prove the need exists
- A list of GitHub issue IDs showing how the roadmap has (or has not) addressed it
- A verdict: **IGNORED**, **UNDER-PRIORITIZED**, or **MISUNDERSTOOD**

---

## How It Works — The Pipeline

We built a five-stage pipeline plus an optional QA layer. Each production stage does one job, produces one output file, and can be inspected independently.

### Stage 1 — Ingest ✅
Pull 9,771 user reviews from HuggingFace and 4,004 GitHub issues from the PPSSPP repository. Every record gets a stable ID that never changes. IDs are the evidence currency of the entire system — every finding can be traced back to the exact reviews and issues that support it.

### Stage 2 — Cluster ✅
Convert each review into a mathematical representation of its meaning (an "embedding"), compress the space using UMAP, then use HDBSCAN to find natural groupings. Reviews that circle the same underlying problem land in the same cluster — without anyone telling the algorithm what to look for. Result: **23 clusters** from 2,905 substantive reviews.

### Stage 3 — Label ✅ (Label agent)
For each cluster, the **Label agent** (Anthropic Claude) reads a sample of reviews and names the latent need: theme, one-sentence need, evidence summary. Cached to `data/label_cache/`.

### Stage 4 — Match ✅ (Match agent)
Compare each labeled cluster against GitHub issues using embedding similarity. Rule-based verdicts (IGNORED / UNDER-PRIORITIZED / MISUNDERSTOOD). The **Match agent** (Claude) is only called for ambiguous cases when an active open issue exists.

### Stage 5 — Score ✅
Calculate confidence from an explicit formula (35% volume + 20% tightness + 45% gap clarity). Merge duplicate clusters, rank gaps, write `gaps.json`.

### QA — Quality tester ✅ (QA critic agent, optional)
After the pipeline, run `make qa`. The **QA critic agent** (Claude) grades each headline gap: is it a latent need or a complaint summary? Writes `data/gaps_qa.json` with pass/warn/fail, pitch tips, and evidence alignment notes. **Does not change scores or ranking.**

---

## Why This Approach Is Different

Most tools that analyze app reviews do one of two things:

1. **Summarize complaints** — "Users often mention crashes and slow loading." This is obvious and not useful. Any product manager already knows their top complaints.

2. **Ask AI to guess** — "Based on these reviews, here are the top user needs." This sounds smart but is not auditable. You cannot defend an AI's opinion to a room of stakeholders.

We do neither of those things.

Instead we use a method that is **deterministic and auditable at every step**:

- Reviews are grouped by a clustering algorithm — not by AI opinion
- A confidence score is calculated by an explicit mathematical formula — not estimated
- **Three Anthropic Claude agents** assist with narrow jobs:
  - **Label agent** — names each cluster as a plain-language need
  - **Match agent** — resolves ambiguous roadmap verdicts
  - **QA critic agent** — tests output quality (latent need vs complaint summary); optional via `make qa`
- Every output can be traced back to specific review IDs and issue IDs — nothing is vague

This means every gap we surface can be defended with evidence. Not "the AI said so" — but "here are 110 reviews, here is their cluster, here is the formula score, and here is why the roadmap misses this."

---

## Why PPSSPP?

PPSSPP is a free, open-source PlayStation Portable emulator for Android. It is available on F-Droid (an open-source app store) and has a large, passionate user base.

We chose it because:

- It has **9,771 user reviews** in our dataset — enough to find statistically meaningful patterns
- Its GitHub repository has **4,004 real issues** and **70 milestones** — a rich roadmap to compare against
- It is a complex app with genuine tension between what users want (more game compatibility, better controls, smoother performance) and what a small open-source team can realistically deliver
- That tension is exactly where unmet needs live

---

## Who This Is For

**Open-source maintainers** who want to understand their users but don't have time to read thousands of reviews.

**Product teams** at any company with a public app and a GitHub issue tracker.

**Researchers** studying the gap between user needs and software roadmaps.

**Anyone** who believes that the people using a product should have a real voice in what gets built — even if they never attend a planning meeting.

---

## The Bigger Picture

The tools that shape software products — GitHub, Jira, Linear, roadmap decks — are all designed for the team. They are excellent at capturing what the team thinks and plans. But they have no input channel for the people who actually use the product every day.

App store reviews are the closest thing to a user's voice that exists at scale. They are unfiltered, unsolicited, and honest in a way that surveys never are. But they are also messy, repetitive, and hard to act on without processing.

Silent Stakeholder processes them. It turns thousands of individual voices into a structured, ranked, evidence-backed list of what users actually need — and holds that list up against what the team has decided to build.

The gap between those two things is where products fail and where opportunities are lost.

We are here to make that gap visible.
