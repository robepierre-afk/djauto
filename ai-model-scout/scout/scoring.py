"""Rank candidates and link them to this week's news."""

from __future__ import annotations

import math
import re

from .models import ModelCandidate, NewsItem
from .textutil import days_ago, family_key, is_non_commercial

TOP_LABS = {"qwen", "deepseek-ai", "meta-llama", "mistralai", "google", "zai-org", "moonshotai",
            "minimaxai", "openai", "nvidia", "microsoft", "allenai"}


def attach_mentions(cands: list[ModelCandidate], news: list[NewsItem]) -> None:
    titles = [(n, f"{n.title} {n.summary}".lower()) for n in news]
    for c in cands:
        keys = {family_key(c.name), c.name.lower()}
        keys = {k for k in keys if len(k) >= 4}
        for n, text in titles:
            if any(re.search(rf"(?<![a-z0-9]){re.escape(k)}", text) for k in keys):
                c.mentions.append(n.title)
                c.mention_urls.append(n.url)


def score(c: ModelCandidate, lookback_days: int) -> float:
    popularity = math.log10(1 + c.likes) * 2 + math.log10(1 + c.downloads) * 0.6 + math.log10(1 + c.stars) * 2
    momentum = math.log10(1 + c.trending) * 3
    age = days_ago(c.created or c.updated)
    recency = 4.0 if age <= lookback_days else 2.0 if age <= 60 else 0.5 if age <= 180 else 0.0
    buzz = min(len(c.mentions), 6) * 1.5
    s = popularity + momentum + recency + buzz
    if c.category == "llm":
        if c.repo_id.split("/")[0].lower() in TOP_LABS:
            s += 2
        if c.params_b:
            s += min(math.log2(1 + c.params_b), 10) * 0.6   # bigger open models tend to be stronger
        if c.has_gguf:
            s += 1
    else:
        if c.watchlisted:
            s += 2
        if age <= 30 and c.source == "github":
            s += 1  # recently updated tool
    return round(s, 2)


def license_note(c: ModelCandidate) -> str:
    notes = []
    if c.license in ("", "unknown"):
        notes.append("licence not stated")
    elif is_non_commercial(c.license):
        notes.append("non-commercial licence")
    if c.gated:
        notes.append("accept terms on Hugging Face to download")
    return "; ".join(notes)


def rank(cands: list[ModelCandidate], lookback_days: int) -> list[ModelCandidate]:
    for c in cands:
        c.score = score(c, lookback_days)
        c.license_note = license_note(c)
    return sorted(cands, key=lambda c: c.score, reverse=True)
