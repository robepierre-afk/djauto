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

    def _get(self, url: str, params: dict | None = None):
        try:
            return http.get_json(url, params, self.headers)
        except http.FetchError as e:
            if "401" not in str(e) or "Authorization" not in self.headers:
                raise
            log.warning("GITHUB_TOKEN was rejected (check .env); continuing without it")
            self.headers.pop("Authorization")
            return http.get_json(url, params, self.headers)

    def collect_music(self, watch_repos: list[str]) -> list[ModelCandidate]:
        seen: dict[str, ModelCandidate] = {}
        failures: list[str] = []
        min_stars = self.cfg.get("min_stars", 50)
        for q in self.cfg.get("music_queries", []):
            query = f"{q} stars:>={min_stars} pushed:>{self.pushed_after}"
            try:
                data = self._get(f"{API}/search/repositories",
                                 {"q": query, "sort": "stars", "order": "desc", "per_page": 15})
            except http.FetchError as e:
                log.warning("GitHub search %r failed: %s", q, e)
                failures.append(str(e))
                continue
            for repo in data.get("items", []):
                seen.setdefault(repo["full_name"], self._to_candidate(repo))
        for full in watch_repos:
            if full in seen:
                seen[full].watchlisted = True
                continue
            try:
                repo = self._get(f"{API}/repos/{full}")
            except http.FetchError as e:
                log.warning("GitHub repo %s failed: %s", full, e)
                failures.append(str(e))
                continue
            c = self._to_candidate(repo)
            c.watchlisted = True
            seen[full] = c
        if not seen and failures:
            # Report the actual cause (rate limit, firewall, bad token) instead of "returned nothing".
            raise http.FetchError(f"all {len(failures)} requests failed, e.g. {failures[-1].split(' failed: ')[-1]}")
        return list(seen.values())

    @staticmethod
    def _to_candidate(repo: dict) -> ModelCandidate:
        topics = repo.get("topics") or []
        desc = repo.get("description") or ""
        lic = (repo.get("license") or {}).get("spdx_id") or "unknown"
        return ModelCandidate(
            repo_id=repo["full_name"],
            category=music_category(" ".join([desc, *topics]), repo["full_name"]),
            source="github", url=repo["html_url"], license=lic.lower() if lic != "NOASSERTION" else "unknown",
            stars=int(repo.get("stargazers_count") or 0), created=iso_date(repo.get("created_at")),
            updated=iso_date(repo.get("pushed_at")), description=desc, tags=topics,
        )
