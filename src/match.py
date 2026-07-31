"""
Stage 4 — Match each labeled theme to GitHub issues via embedding similarity,
then assign a verdict: IGNORED | UNDER-PRIORITIZED | MISUNDERSTOOD.

Input:  data/labeled_clusters.json + data/issues.json
Output: data/matches.json  (cluster_id -> {issue_ids, verdict, reasoning})
"""

# TODO: implement embed_issues(issues) -> np.ndarray
# TODO: implement match_theme_to_issues(theme_vec, issue_vecs, issues) -> list[dict]
# TODO: implement assign_verdict(matched_issues) -> str  (rule-based from label/status)
# TODO: write main() that runs matching for all themes and saves matches.json
