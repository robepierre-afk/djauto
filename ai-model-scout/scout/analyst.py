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
each with an estimate of whether it fits their hardware, and any capability ratings already \
researched (1-5 per area, compared with the paid frontier). Keep your verdicts consistent with those \
ratings unless you find newer evidence. Use web search to check current, independent \
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


def claude_client(cfg: dict, purpose: str):
    """Return an Anthropic client, or None (with a log line) if Claude isn't set up."""
    if not cfg.get("analyst", {}).get("enabled", True):
        return None
    try:
        import anthropic
    except ImportError:
        log.info("anthropic package not installed; skipping the %s", purpose)
        return None
    if not cfg["secrets"].get("ANTHROPIC_API_KEY"):
        log.info("ANTHROPIC_API_KEY not set; skipping the %s", purpose)
        return None
    return anthropic.Anthropic()


def ask_claude(client, cfg: dict, purpose: str, system: str, messages: list[dict], *,
               web_searches: int = 0, json_schema: dict | None = None, effort: str | None = None) -> str | None:
    """One Claude request (resuming if a web-search turn pauses). Returns the text, or None on failure."""
    import anthropic

    acfg = cfg.get("analyst", {})
    output_config: dict = {"effort": effort or acfg.get("effort", "medium")}
    if json_schema:
        output_config["format"] = {"type": "json_schema", "schema": json_schema}
    extra = {}
    if web_searches:
        extra["tools"] = [{"type": "web_search_20260209", "name": "web_search", "max_uses": web_searches}]
    messages = list(messages)
    try:
        for _ in range(5):  # resume if the server-side search loop pauses
            with client.beta.messages.stream(
                model=acfg.get("model", "claude-opus-5-5"),
                max_tokens=64000,
                system=system,
                thinking={"type": "adaptive"},
                output_config=output_config,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=messages,
                **extra,
            ) as stream:
                response = stream.get_final_message()
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            break
    except anthropic.RateLimitError as e:
        log.warning("Claude rate limit; skipping the %s: %s", purpose, e)
        return None
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s; skipping the %s: %s", e.status_code, purpose, e.message)
        return None
    except anthropic.APIConnectionError as e:
        log.warning("Could not reach the Claude API; skipping the %s: %s", purpose, e)
        return None

    if response.stop_reason == "refusal":
        log.warning("The %s request was declined; skipping", purpose)
        return None
    if response.stop_reason == "max_tokens":
        log.warning("The %s was cut off at the token limit; skipping", purpose)
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text or None


def write_briefing(cfg: dict, machine: dict, llms: list[ModelCandidate], music: list[ModelCandidate],
                   news: list[NewsItem], ratings: dict | None = None) -> str | None:
    client = claude_client(cfg, "written briefing")
    if client is None:
        return None
    payload = {
        "machine": machine,
        "llm_candidates": [_compact(c) for c in llms[:40]],
        "music_candidates": [_compact(c) for c in music[:40]],
        "ratings": ratings or {},
        "news": [{"title": n.title, "source": n.source, "channel": n.channel, "date": n.published,
                  "url": n.url, "topic": n.topic} for n in news[:60]],
    }
    messages = [{"role": "user", "content": "This week's findings:\n\n" + json.dumps(payload, indent=1)}]
    return ask_claude(client, cfg, "written briefing", SYSTEM, messages,
                      web_searches=int(cfg.get("analyst", {}).get("max_searches", 12)))
