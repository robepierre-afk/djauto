"""Helpers for pulling facts out of model names, tags and free text."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_SIZE_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*([bm])(?![a-z])", re.I)
_MOE_RE = re.compile(r"(\d+(?:\.\d+)?)b[-_]a(\d+(?:\.\d+)?)b", re.I)
_EXPERTS_RE = re.compile(r"(\d+)x(\d+(?:\.\d+)?)b", re.I)

# Keyword lists are matched against whole words (hyphens/underscores count as spaces),
# so "stem" doesn't match "system" and "mir" doesn't match "mirror".
SCORE_WORDS = ("score", "sheet music", "notation", "omr", "optical music", "transcription", "transcribe",
               "transcriber", "audio to midi", "musicxml", "abc notation", "symbolic music", "piano roll",
               "basic pitch", "mt3")
ANALYSIS_WORDS = ("music analysis", "music tagging", "tagger", "beat tracking", "beat", "downbeat", "chord",
                  "chord recognition", "key detection", "tempo", "source separation", "separation", "demucs",
                  "stem", "stems", "mert", "mir", "music information retrieval", "music classification",
                  "music captioning", "music understanding", "embedding", "all in one", "pitch estimation",
                  "madmom", "essentia")
GENERATION_WORDS = ("music generation", "text to music", "song generation", "musicgen", "audiocraft", "ace step",
                    "acestep", "yue", "diffrhythm", "stable audio", "riffusion", "accompaniment", "instrumental",
                    "singing voice", "lyrics to song", "song", "songs", "loops", "samples")
MUSIC_WORDS = ("music", "musical", "song", "songs", "singing", "singer", "melody", "midi", "lyrics",
               "accompaniment", "instrumental", "piano", "guitar", "drum", "drums", "chord", "chords",
               "beat tracking", "stem separation", "demucs", "musicgen", "audiocraft", "ace step", "acestep",
               "yue", "diffrhythm", "stable audio", "riffusion", "mert", "musicxml", "sheet music",
               "symbolic music", "source separation", "music transcription")
# Speech/voice models are excluded unless their *name* says they're about music.
SPEECH_WORDS = ("tts", "text to speech", "speech", "voice", "asr", "speaker", "parler", "whisper")
# Building blocks rather than something you'd run on its own.
COMPONENT_WORDS = ("tokenizer", "codec", "vae", "lora")


def _words(text: str) -> str:
    return " " + " ".join(re.split(r"[^a-z0-9]+", text.lower())) + " "


def _hits(words: str, keywords) -> int:
    return sum(f" {_words(k).strip()} " in words for k in keywords)


def music_category(text: str, name: str = "", pipeline: str = "") -> str:
    """Pick generation / analysis / score. Words in the repo name count three times as much as tags."""
    w, n = _words(text), _words(name)
    # On a tie the more specific category wins: a "acestep-transcriber" is a transcriber.
    scores = {
        "music_score": _hits(w, SCORE_WORDS) + 3 * _hits(n, SCORE_WORDS),
        "music_analysis": _hits(w, ANALYSIS_WORDS) + 3 * _hits(n, ANALYSIS_WORDS),
        "music_generation": _hits(w, GENERATION_WORDS) + 3 * _hits(n, GENERATION_WORDS)
        + (3 if pipeline == "text-to-audio" else 0),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "music_generation"


def is_music(text: str, name: str = "") -> bool:
    w = _words(text)
    if not _hits(w, MUSIC_WORDS):
        return False
    if name:
        n = _words(name)
        if _hits(n, COMPONENT_WORDS):
            return False
        if _hits(w, SPEECH_WORDS) and not _hits(n, MUSIC_WORDS):
            return False
    return True


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
