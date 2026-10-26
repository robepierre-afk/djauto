"""Optional: Claude reads the week's findings, checks current benchmarks on the web,
and writes a short briefing with concrete recommendations for your machine."""

from __future__ import annotations

import json
import logging

from .hardware import FIT_LABEL
from .models import ModelCandidate, NewsItem

log = logging.getLogger(__name__)

SYSTEM = """You are a hands-on AI tooling advisor writing a weekly briefing for a musician and \
producer who runs AI models locally on their own media machine. They only want models with free, \
downloadable weights they can run themselves.

You get this week's candidates (from Hugging Face, GitHub, YouTube, Reddit, Hacker News and arXiv), \
each with an estimate of whether it fits their hardware. Use web search to check current, independent \
evidence (LMArena, Artificial Analysis, LiveBench, vendor model cards, credible reviews) on how the \
strongest open-weight LLMs compare with the leading paid models (Claude, ChatGPT, Gemini). Cite the \
sources you rely on as Markdown links. Prefer facts over hype; say plainly when evidence is thin.

Write Markdown with exactly these sections:
## Bottom line
Three to five bullets: what changed this week and what to download.
## Open LLMs vs Claude / ChatGPT
Which open-weight models come closest to the paid frontier today, on what tasks, with numbers where \
you found them. Name the gaps honestly.
## Best picks for this machine
One pick each for: general assistant, coding, reasoning, fast/small. Give the exact repo, the quant \
to use, and the app to run it in (Ollama, LM Studio, llama.cpp, vLLM).
## Music: generation, analysis and scores
Best current picks for song/instrumental generation, stem separation and analysis (beats, chords, \
key, structure), and audio-to-MIDI / sheet-music (MusicXML) work. Flag non-commercial licences.
## Worth watching
New releases or papers that aren't ready yet but may be soon.

Keep it under about 700 words. Do not invent repos, numbers or licences."""


def _compact(c: ModelCandidate) -> dict:
    return {k: v for k, v in {
        "repo": c.repo_id, "category": c.category, "url": c.url, "license": c.license,
        "params_b": c.params_b, "active_b": c.active_params_b, "likes": c.likes, "stars": c.stars,
        "created": c.created, "updated": c.updated, "gguf": c.has_gguf, "fit": FIT_LABEL.get(c.fit, c.fit),
        "fit_detail": c.fit_detail, "new_this_week": c.is_new, "mentions": c.mentions[:3],
        "desc": c.description[:160],
    }.items() if v not in (None, "", [], False)}


def write_briefing(cfg: dict, machine: dict, llms: list[ModelCandidate], music: list[ModelCandidate],
                   news: list[NewsItem]) -> str | None:
    acfg = cfg.get("analyst", {})
    if not acfg.get("enabled", True):
        return None
    try:
        import anthropic
    except ImportError:
        log.info("anthropic package not installed; skipping the written briefing")
        return None
    if not cfg["secrets"].get("ANTHROPIC_API_KEY"):
        log.info("ANTHROPIC_API_KEY not set; skipping the written briefing")
        return None

    payload = {
        "machine": machine,
        "llm_candidates": [_compact(c) for c in llms[:40]],
        "music_candidates": [_compact(c) for c in music[:40]],
        "news": [{"title": n.title, "source": n.source, "channel": n.channel, "date": n.published,
                  "url": n.url, "topic": n.topic} for n in news[:60]],
    }
    messages = [{"role": "user", "content": "This week's findings:\n\n" + json.dumps(payload, indent=1)}]

    client = anthropic.Anthropic()
    try:
        for _ in range(5):  # resume if the server-side search loop pauses
            with client.beta.messages.stream(
                model=acfg.get("model", "claude-opus-5-5"),
                max_tokens=64000,
                system=SYSTEM,
                thinking={"type": "adaptive"},
                output_config={"effort": acfg.get("effort", "medium")},
                tools=[{"type": "web_search_20260209", "name": "web_search",
                        "max_uses": int(acfg.get("max_searches", 12))}],
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=messages,
            ) as stream:
                response = stream.get_final_message()
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            break
    except anthropic.RateLimitError as e:
        log.warning("Claude rate limit; skipping briefing: %s", e)
        return None
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s; skipping briefing: %s", e.status_code, e.message)
        return None
    except anthropic.APIConnectionError as e:
        log.warning("Could not reach the Claude API; skipping briefing: %s", e)
        return None

    if response.stop_reason == "refusal":
        log.warning("Briefing request was declined; skipping")
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text or None
