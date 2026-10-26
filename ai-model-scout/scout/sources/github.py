"""GitHub: music AI tools often ship as repos with downloadable checkpoints."""

from __future__ import annotations

import logging

from .. import http
from ..models import ModelCandidate
from ..textutil import iso_date, music_category, since

API = "https://api.github.com"
log = logging.getLogger(__name__)


class GitHub:
    def __init__(self, cfg: dict, token: str = "", lookback_days: int = 14):
        self.cfg = cfg.get("github", {})
        self.headers = {"Accept": "application/vnd.github+json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        # Repos must have been pushed within the year; stars do the ranking.
        self.pushed_after = since(max(lookback_days, 365)).date().isoformat()

    def collect_music(self, watch_repos: list[str]) -> list[ModelCandidate]:
        seen: dict[str, ModelCandidate] = {}
        min_stars = self.cfg.get("min_stars", 50)
        for q in self.cfg.get("music_queries", []):
            query = f"{q} stars:>={min_stars} pushed:>{self.pushed_after}"
            try:
                data = http.get_json(f"{API}/search/repositories",
                                     {"q": query, "sort": "stars", "order": "desc", "per_page": 15},
                                     self.headers)
            except http.FetchError as e:
                log.warning("GitHub search %r failed: %s", q, e)
                continue
            for repo in data.get("items", []):
                seen.setdefault(repo["full_name"], self._to_candidate(repo))
        for full in watch_repos:
            if full in seen:
                seen[full].watchlisted = True
                continue
            try:
                repo = http.get_json(f"{API}/repos/{full}", headers=self.headers)
            except http.FetchError as e:
                log.warning("GitHub repo %s failed: %s", full, e)
                continue
            c = self._to_candidate(repo)
            c.watchlisted = True
            seen[full] = c
        return list(seen.values())

    @staticmethod
    def _to_candidate(repo: dict) -> ModelCandidate:
        topics = repo.get("topics") or []
        desc = repo.get("description") or ""
        lic = (repo.get("license") or {}).get("spdx_id") or "unknown"
        return ModelCandidate(
            repo_id=repo["full_name"],
            category=music_category(" ".join([repo["full_name"], desc, *topics])),
            source="github", url=repo["html_url"], license=lic.lower() if lic != "NOASSERTION" else "unknown",
            stars=int(repo.get("stargazers_count") or 0), created=iso_date(repo.get("created_at")),
            updated=iso_date(repo.get("pushed_at")), description=desc, tags=topics,
        )
