"""Industry rating matrix: how each model scores per capability, next to the leading paid products.

Two Claude calls, because web-search results carry citations and structured JSON output can't be
combined with citations:
  1. research: search the web for benchmark results and reviews, write evidence notes per model;
  2. structure: turn those notes into fixed 1-5 scores (JSON schema, no tools).
Ratings are cached in state.json and only refreshed once they're older than `max_age_days`, so a
model is researched about once a month rather than every week.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from .analyst import ask_claude, claude_client
from .models import ModelCandidate
from .textutil import days_ago

log = logging.getLogger(__name__)

# Capability areas per group: (key, column label, what the score means).
DIMENSIONS = {
    "llm": [
        ("coding", "Coding", "writing and fixing code (SWE-bench, LiveCodeBench, Aider)"),
        ("reasoning", "Reasoning & maths", "multi-step reasoning and maths (GPQA, AIME, HLE)"),
        ("knowledge", "Knowledge", "general knowledge and factual accuracy (MMLU-Pro, SimpleQA)"),
        ("writing", "Writing & chat", "writing quality and conversation (LMArena, creative writing evals)"),
        ("agents", "Tools & agents", "tool calling and multi-step agent tasks (BFCL, tau-bench, Terminal-Bench)"),
        ("multilingual", "Multilingual", "languages other than English"),
        ("long_context", "Long context", "using long documents accurately (RULER, MRCR)"),
        ("vision", "Vision", "understanding images; 0 if it has no image input"),
    ],
    "music_generation": [
        ("vocals", "Vocals", "sung vocal quality and intelligibility"),
        ("instrumentals", "Instrumentals", "instrument realism and mix quality"),
        ("structure", "Song structure", "verse/chorus structure, coherent full-length songs"),
        ("lyrics", "Lyrics adherence", "sings the given lyrics accurately"),
        ("control", "Control & editing", "style/genre prompting, reference audio, edit/extend/remix"),
        ("fidelity", "Audio fidelity", "sample rate, artefacts, production polish"),
    ],
    "music_analysis": [
        ("accuracy", "Accuracy", "accuracy on its task versus published benchmarks"),
        ("robustness", "Robustness", "dense mixes, live recordings, many genres"),
        ("coverage", "Coverage", "range of instruments / features it handles"),
        ("outputs", "Outputs", "useful output formats for a producer (stems, MIDI, labels)"),
        ("ease", "Ease of use", "install and run effort for a non-developer"),
    ],
}
DIMENSIONS["music_score"] = [
    ("accuracy", "Accuracy", "note/onset accuracy of transcription or recognition"),
    ("robustness", "Robustness", "polyphony, dense mixes, poor-quality scans or audio"),
    ("coverage", "Coverage", "instruments, voices and notation features handled"),
    ("outputs", "Outputs", "MIDI / MusicXML / notation quality, ready for a score editor"),
    ("ease", "Ease of use", "install and run effort for a non-developer"),
]
GROUP_TITLES = {
    "llm": "Open LLMs vs Claude / ChatGPT / Gemini",
    "music_generation": "Music generation vs paid tools",
    "music_analysis": "Music analysis vs paid tools",
    "music_score": "Transcription & scores vs paid tools",
}
ALL_DIMS = sorted({d for dims in DIMENSIONS.values() for d, _, _ in dims})

SCALE = ("5 = matches or beats the best paid product in that area; 4 = close behind; 3 = solid but clearly "
         "behind; 2 = well behind; 1 = weak; 0 = not applicable or no usable evidence.")

RESEARCH_SYSTEM = f"""You are an AI benchmark analyst. For each model listed, search the web for \
independent evidence of how good it is: leaderboards (LMArena, Artificial Analysis, LiveBench, \
Open LLM leaderboards), benchmark tables in model cards and papers, and credible hands-on reviews. \
For music models use papers, published evaluations, comparisons and reviews from producers.

Also research the reference products you're asked to include (the leading paid products), so the \
open models can be compared with them on the same scale.

For every model, rate each capability area listed for its group on this scale: {SCALE}
Write plain-text notes, one block per model, starting with its exact id as given. For each area give \
the score, the evidence (benchmark name and number where you have one), then one line on what it \
excels at and one on where it falls short. Note how confident you are. Prefer recent, independent \
results over vendor claims and say when a number is vendor-reported. Never invent numbers."""

STRUCTURE_SYSTEM = """Convert the research notes into the JSON schema. Copy scores exactly as the \
notes give them; use 0 where the notes have no score for an area. Keep `excels` and `falls_short` to \
one short sentence each, in plain language a musician would understand. Use the model id exactly as \
written in the notes. Only include URLs that appear in the notes."""

SCHEMA = {
    "type": "object",
    "properties": {
        "ratings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "group": {"type": "string", "enum": list(DIMENSIONS)},
                    "is_reference": {"type": "boolean", "description": "true for paid reference products"},
                    "scores": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "area": {"type": "string", "enum": ALL_DIMS},
                                "score": {"type": "integer", "description": "0-5"},
                            },
                            "required": ["area", "score"],
                            "additionalProperties": False,
                        },
                    },
                    "excels": {"type": "string"},
                    "falls_short": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "group", "is_reference", "scores", "excels", "falls_short",
                             "confidence", "sources"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ratings"],
    "additionalProperties": False,
}

REFERENCES = {
    "llm": "Claude (latest), ChatGPT (latest GPT), Gemini (latest)",
    "music_generation": "Suno (latest), Udio",
    "music_analysis": "the leading paid stem-separation / music-analysis service (e.g. Moises)",
    "music_score": "the leading paid audio-to-score / transcription tool",
}


def _group_of(c: ModelCandidate) -> str:
    return "llm" if c.category == "llm" else c.category


def select(llms: list[ModelCandidate], music: list[ModelCandidate], rcfg: dict) -> list[ModelCandidate]:
    picks = llms[: rcfg.get("llms", 10)]
    for group in ("music_generation", "music_analysis", "music_score"):
        picks += [c for c in music if c.category == group][: rcfg.get("music_per_group", 5)]
    return picks


def rate(cfg: dict, cache: dict, llms: list[ModelCandidate], music: list[ModelCandidate]) -> dict:
    """Return {id: rating} for the selected models plus references, refreshing stale entries in `cache`."""
    rcfg = cfg.get("ratings", {})
    if not rcfg.get("enabled", True):
        return {}
    max_age = int(rcfg.get("max_age_days", 30))
    picks = select(llms, music, rcfg)
    stale = [c for c in picks if days_ago(cache.get(c.repo_id, {}).get("rated", "")) > max_age]

    if stale:
        client = claude_client(cfg, "rating matrix")
        if client is not None:
            fresh = _research(client, cfg, stale)
            today = date.today().isoformat()
            for rid, r in fresh.items():
                cache[rid] = {**r, "rated": today}

    wanted = {c.repo_id for c in picks}
    groups = {_group_of(c) for c in picks}
    return {rid: r for rid, r in cache.items()
            if rid in wanted or (r.get("is_reference") and r.get("group") in groups)}


def _research(client, cfg: dict, models: list[ModelCandidate]) -> dict:
    by_group: dict[str, list[ModelCandidate]] = {}
    for c in models:
        by_group.setdefault(_group_of(c), []).append(c)

    lines = []
    for group, cands in by_group.items():
        dims = "; ".join(f"{key} = {label}: {desc}" for key, label, desc in DIMENSIONS[group])
        lines.append(f"## Group: {group}\nAreas: {dims}\nReference products to rate as well "
                     f"(use is_reference): {REFERENCES[group]}\nModels:")
        lines += [f"- {c.repo_id} ({c.url}; {c.params_b or '?'}B params; licence {c.license})" for c in cands]
        lines.append("")
    request = "\n".join(lines)

    searches = int(cfg.get("ratings", {}).get("max_searches", 25))
    notes = ask_claude(client, cfg, "rating research", RESEARCH_SYSTEM,
                       [{"role": "user", "content": request}], web_searches=searches, effort="high")
    if not notes:
        return {}
    raw = ask_claude(client, cfg, "rating matrix", STRUCTURE_SYSTEM,
                     [{"role": "user", "content": f"Models and areas:\n{request}\n\nResearch notes:\n{notes}"}],
                     json_schema=SCHEMA, effort="low")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("Rating matrix wasn't valid JSON; skipping: %s", e)
        return {}
    return clean(data, {c.repo_id for c in models})


def clean(data: dict, requested: set[str]) -> dict:
    """Keep ratings for models we asked about (plus references), with scores clamped to 0-5."""
    out = {}
    for r in data.get("ratings", []):
        rid = r.get("id", "").strip()
        group = r.get("group")
        if group not in DIMENSIONS or not rid:
            continue
        if rid not in requested and not r.get("is_reference"):
            continue
        valid = {d for d, _, _ in DIMENSIONS[group]}
        scores = {s["area"]: max(0, min(5, int(s["score"]))) for s in r.get("scores", []) if s.get("area") in valid}
        key = rid if rid in requested else f"ref:{group}:{rid}"
        out[key] = {"name": rid, "group": group, "is_reference": rid not in requested, "scores": scores,
                    "excels": r.get("excels", ""), "falls_short": r.get("falls_short", ""),
                    "confidence": r.get("confidence", "low"),
                    "sources": [u for u in r.get("sources", []) if u.startswith("http")][:5]}
    return out
