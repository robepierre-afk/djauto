"""Helpers for pulling facts out of model names, tags and free text."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_SIZE_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*([bm])(?![a-z])", re.I)
_MOE_RE = re.compile(r"(\d+(?:\.\d+)?)b[-_]a(\d+(?:\.\d+)?)b", re.I)
_EXPERTS_RE = re.compile(r"(\d+)x(\d+(?:\.\d+)?)b", re.I)

SCORE_WORDS = ("score", "sheet music", "notation", "omr", "optical music", "transcri", "midi",
               "musicxml", "abc notation", "symbolic", "piano roll")
ANALYSIS_WORDS = ("analysis", "tagging", "tagger", "beat", "chord", "key detection", "tempo",
                  "separation", "demucs", "stem", "mert", "mir", "music-information", "classification",
                  "captioning", "understanding", "embedding", "structure", "all-in-one", "pitch")
MUSIC_WORDS = ("music", "song", "singing", "melody", "midi", "lyrics", "accompaniment", "instrument",
               "piano", "guitar", "drum", "beat", "chord", "stem", "demucs", "musicgen", "audiocraft",
               "ace-step", "yue", "diffrhythm", "stable-audio", "riffusion", "mert", "score", "notation",
               "symbolic")


def parse_params_from_name(name: str) -> tuple[float | None, float | None]:
    """Return (total_b, active_b) guessed from a repo name like 'Qwen3-30B-A3B' or 'Mixtral-8x7B'."""
    n = name.replace("_", "-")
    m = _MOE_RE.search(n)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = _EXPERTS_RE.search(n)
    if m:
        # 8x7B shares attention layers, so real total is ~0.85x the naive product.
        return round(int(m.group(1)) * float(m.group(2)) * 0.85, 1), None
    best = None
    for num, unit in _SIZE_RE.findall(n):
        val = float(num) / (1000 if unit.lower() == "m" else 1)
        best = val if best is None else max(best, val)
    return best, None


def music_category(text: str) -> str:
    t = text.lower()
    if any(w in t for w in SCORE_WORDS):
        return "music_score"
    if any(w in t for w in ANALYSIS_WORDS):
        return "music_analysis"
    return "music_generation"


def is_music(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in MUSIC_WORDS)


def is_non_commercial(license_id: str) -> bool:
    lic = license_id.lower()
    return any(w in lic for w in ("-nc", "non-commercial", "noncommercial", "research"))


def family_key(repo_name: str) -> str:
    """'Qwen3-235B-A22B-Instruct-2507' -> 'qwen3'; used to match news titles to models."""
    base = re.split(r"[-_ ](?:\d+(?:\.\d+)?[bm]\b|instruct|chat|base|it\b|a\d+b|gguf|fp8|awq)", repo_name,
                    maxsplit=1, flags=re.I)[0]
    return base.lower().strip("-_ ")


def iso_date(value: str | None) -> str:
    return (value or "")[:10]


def days_ago(iso: str) -> float:
    if not iso:
        return 1e9
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return 1e9
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)
