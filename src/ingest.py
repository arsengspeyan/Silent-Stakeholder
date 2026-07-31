"""
Stage 1 — Ingest

Pulls both sides of the pipeline into locally cached JSON files:
  data/reviews.json    — filtered app reviews from HuggingFace (sealuzh/app_reviews)
  data/issues.json     — GitHub issues (real issues only, PRs excluded)
  data/milestones.json — GitHub milestones

Every record gets a stable ID that never changes between runs.
IDs are the evidence currency for the entire pipeline — never drop them.

Usage:
    python src/ingest.py            # uses cache if data files exist
    python src/ingest.py --refresh  # re-fetches everything from source
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from datasets import load_dataset
from dotenv import load_dotenv

# ── constants ────────────────────────────────────────────────────────────────

PACKAGE_NAME = "org.ppsspp.ppsspp"
GITHUB_REPO  = "hrydgard/ppsspp"  # owner/repo
DATA_DIR     = Path(__file__).parent.parent / "data"

REVIEWS_FILE    = DATA_DIR / "reviews.json"
ISSUES_FILE     = DATA_DIR / "issues.json"
MILESTONES_FILE = DATA_DIR / "milestones.json"


# ── reviews ──────────────────────────────────────────────────────────────────

def fetch_reviews() -> list[dict]:
    """
    Load the full sealuzh/app_reviews HuggingFace dataset, filter to our app,
    sort by (date, review_text) for determinism, then assign stable IDs.

    Stable ID contract: same review always gets the same ID across runs because
    we sort before enumerating — IDs never depend on download order.
    """
    print(f"Loading sealuzh/app_reviews from HuggingFace (filtering to {PACKAGE_NAME})…")
    ds = load_dataset("sealuzh/app_reviews", split="train")

    # Filter to our package
    rows = [r for r in ds if r["package_name"] == PACKAGE_NAME]
    print(f"  Found {len(rows):,} raw reviews for {PACKAGE_NAME}")

    # Deterministic sort so IDs are stable regardless of dataset iteration order
    rows.sort(key=lambda r: (r.get("date") or "", r.get("review") or ""))

    reviews = []
    for i, row in enumerate(rows):
        reviews.append({
            "id":           f"rev_{i+1:04d}",
            "package_name": row["package_name"],
            "text":         row["review"],
            "date":         row.get("date"),
            "stars":        row.get("star"),
        })

    return reviews


# ── github helpers ────────────────────────────────────────────────────────────

def github_session(token: str) -> requests.Session:
    """Build a requests Session with auth headers pre-set."""
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return s


def paginate(session: requests.Session, url: str, params: dict) -> list[dict]:
    """
    Fetch all pages from a GitHub REST endpoint.
    Respects rate-limit headers: if we're out of calls, prints a clear message
    and waits until the reset time rather than crashing silently.
    """
    results = []
    page = 1
    while True:
        resp = session.get(url, params={**params, "page": page, "per_page": 100})

        # Rate-limit handling
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset_ts = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(reset_ts - int(time.time()), 1)
            print(f"  GitHub rate-limited — waiting {wait}s until reset…")
            time.sleep(wait)
            continue  # retry same page

        # GitHub caps pagination at page 100 (10 000 items); 422 = beyond that limit
        if resp.status_code == 422:
            print(f"  Reached GitHub's 10 000-item pagination cap at page {page} — stopping.")
            break

        resp.raise_for_status()
        batch = resp.json()

        if not batch:
            break  # no more pages

        results.extend(batch)
        page += 1

    return results


# ── issues ────────────────────────────────────────────────────────────────────

def fetch_issues(session: requests.Session) -> list[dict]:
    """
    Pull all GitHub issues (state=all).  The issues endpoint also returns PRs;
    we drop any record that has a 'pull_request' key — real issues never have it.
    ID = GitHub issue number (stable forever, even if issues are deleted).
    """
    owner, repo = GITHUB_REPO.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    print(f"Fetching GitHub issues from {GITHUB_REPO} (all states, paginated)…")

    raw = paginate(session, url, {"state": "all"})

    issues = []
    pr_count = 0
    for item in raw:
        if "pull_request" in item:
            pr_count += 1
            continue  # skip PRs

        issues.append({
            "id":         item["number"],          # GitHub issue number — our stable ID
            "title":      item["title"],
            "body":       item.get("body") or "",
            "state":      item["state"],            # "open" or "closed"
            "labels":     [l["name"] for l in item.get("labels", [])],
            "milestone":  item["milestone"]["title"] if item.get("milestone") else None,
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        })

    print(f"  {len(raw):,} total records — dropped {pr_count} PRs → {len(issues):,} real issues")
    return issues


# ── milestones ────────────────────────────────────────────────────────────────

def fetch_milestones(session: requests.Session) -> list[dict]:
    """
    Pull all milestones (state=all) so we can later assess roadmap coverage.
    ID = GitHub milestone number (stable).
    """
    owner, repo = GITHUB_REPO.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/milestones"
    print(f"Fetching GitHub milestones from {GITHUB_REPO}…")

    raw = paginate(session, url, {"state": "all"})

    milestones = []
    for m in raw:
        milestones.append({
            "id":           m["number"],
            "title":        m["title"],
            "description":  m.get("description") or "",
            "state":        m["state"],
            "open_issues":  m["open_issues"],
            "closed_issues": m["closed_issues"],
            "due_on":       m.get("due_on"),
        })

    return milestones


# ── cache helpers ─────────────────────────────────────────────────────────────

def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest reviews and GitHub data.")
    parser.add_argument("--refresh", action="store_true",
                        help="Ignore cache and re-fetch everything from source.")
    args = parser.parse_args()

    load_dotenv()
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("ERROR: GITHUB_TOKEN not set. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)

    # ── reviews ──
    if not args.refresh and REVIEWS_FILE.exists():
        print(f"Cache hit: loading reviews from {REVIEWS_FILE}")
        reviews = load_json(REVIEWS_FILE)
    else:
        reviews = fetch_reviews()
        save_json(REVIEWS_FILE, reviews)
        print(f"  Saved {len(reviews):,} reviews → {REVIEWS_FILE}")

    # ── issues + milestones ──
    if not args.refresh and ISSUES_FILE.exists() and MILESTONES_FILE.exists():
        print(f"Cache hit: loading issues from {ISSUES_FILE}")
        issues = load_json(ISSUES_FILE)
        print(f"Cache hit: loading milestones from {MILESTONES_FILE}")
        milestones = load_json(MILESTONES_FILE)
    else:
        session = github_session(github_token)
        issues = fetch_issues(session)
        save_json(ISSUES_FILE, issues)
        print(f"  Saved {len(issues):,} issues → {ISSUES_FILE}")

        milestones = fetch_milestones(session)
        save_json(MILESTONES_FILE, milestones)
        print(f"  Saved {len(milestones):,} milestones → {MILESTONES_FILE}")

    # ── summary ──
    print("\n── Ingest summary ──────────────────────────────")
    print(f"  Reviews   : {len(reviews):,}  ({REVIEWS_FILE})")
    print(f"  Issues    : {len(issues):,}  ({ISSUES_FILE})")
    print(f"  Milestones: {len(milestones):,}  ({MILESTONES_FILE})")
    print("────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
