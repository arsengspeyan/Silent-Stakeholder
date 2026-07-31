"""
Stage 1 — Ingest reviews from HuggingFace (sealuzh/app_reviews) and
GitHub issues/milestones via api.github.com.

Outputs stable-ID dicts written to data/reviews.json and data/issues.json.
"""

# TODO: implement fetch_reviews(app_package, max_rows) -> list[dict]
# TODO: implement fetch_github_issues(owner, repo, token) -> list[dict]
# TODO: write main() that saves both to data/
