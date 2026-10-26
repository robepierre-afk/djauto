"""Remembers what earlier runs saw, so each report can flag what's new."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"seen": {}, "youtube_channels": {}, "runs": []}
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    @property
    def channel_cache(self) -> dict:
        return self.data["youtube_channels"]

    @property
    def first_run(self) -> bool:
        return not self.data["runs"]

    def mark(self, repo_ids: list[str]) -> set[str]:
        """Record ids; return the ones never seen before."""
        today = date.today().isoformat()
        new = {r for r in repo_ids if r not in self.data["seen"]}
        for r in new:
            self.data["seen"][r] = today
        return new

    def save(self, report_path: str) -> None:
        self.data["runs"] = (self.data["runs"] + [{"date": date.today().isoformat(), "report": report_path}])[-52:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
