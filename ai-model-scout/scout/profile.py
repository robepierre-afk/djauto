"""'Good for' labels and a profile page per model: what it is, how it rates, where to read more."""

from __future__ import annotations

import html
import re
from urllib.parse import quote_plus

from .hardware import FIT_LABEL
from .models import ModelCandidate
from .page import HTML_TEMPLATE
from .ratings import DIMENSIONS, GROUP_TITLES, SCALE
from .textutil import _hits, _words, is_non_commercial

# (label, keywords) checked against the name, tags and model-card summary.
LLM_USES = [
    ("Coding", ("coder", "code", "coding", "swe", "devstral", "codestral", "programming")),
    ("Reasoning & maths", ("thinking", "reasoning", "reasoner", "r1", "math", "maths", "qwq")),
    ("Vision", ("vl", "vision", "image text to text", "omni", "multimodal", "image understanding")),
    ("Tools & agents", ("agent", "agentic", "tool calling", "function calling", "tool use")),
    ("Writing", ("writer", "writing", "story", "storytelling", "roleplay", "creative", "humanizer", "humanize")),
    ("Long documents", ("long context", "1m context", "long document")),
    ("Multilingual", ("multilingual", "translation")),
]
MUSIC_USES = {
    "music_generation": [
        ("Full songs with vocals", ("song", "songs", "lyrics", "vocals", "lyrics to song", "song generation")),
        ("Instrumentals & samples", ("instrumental", "samples", "loops", "sound effects", "stable audio",
                                     "musicgen", "text to music")),
        ("Singing voice", ("singing voice", "svs", "svc", "voice conversion")),
    ],
    "music_analysis": [
        ("Stem separation", ("separation", "demucs", "stems", "stem", "source separation")),
        ("Beats & tempo", ("beat", "beats", "downbeat", "tempo", "bpm")),
        ("Chords & key", ("chord", "chords", "key detection")),
        ("Song structure", ("structure", "sections", "all in one", "segmentation")),
        ("Tagging & search", ("mert", "tagging", "tagger", "embedding", "classification", "captioning")),
    ],
    "music_score": [
        ("Audio → MIDI", ("midi", "basic pitch", "mt3", "piano transcription", "audio to midi", "transcription")),
        ("Sheet music recognition", ("omr", "optical music", "oemer", "sheet music")),
        ("Lyrics transcription", ("lyrics transcription", "lyric transcription", "transcriber")),
        ("MusicXML / notation", ("musicxml", "notation", "abc notation", "symbolic music", "score")),
    ],
}
DEFAULT_USE = {"llm": "General assistant", "music_generation": "Music generation",
               "music_analysis": "Music analysis", "music_score": "Transcription"}


def overall(rating: dict | None) -> float | None:
    vals = [v for v in (rating or {}).get("scores", {}).values() if v]
    return round(sum(vals) / len(vals), 1) if vals else None


def good_for(c: ModelCandidate, rating: dict | None = None) -> list[str]:
    """Rated strengths win (scores of 4-5); otherwise infer from the name, tags and card."""
    group = c.category
    if rating and rating.get("scores"):
        labels = {d: label for d, label, _ in DIMENSIONS[group]}
        ranked = sorted(((v, d) for d, v in rating["scores"].items() if v), reverse=True)
        strong = [labels[d] for v, d in ranked if v >= 4][:3]
        if strong:
            return strong
    name, text = _words(c.name), _words(" ".join([c.name, c.pipeline_tag, *c.tags, c.description, c.summary]))
    # Labels named in the repo name come first, then ones the tags or model card mention.
    from_name, from_text = [], []
    for label, kws in (LLM_USES if group == "llm" else MUSIC_USES[group]):
        if _hits(name, kws) or (label == "Vision" and c.pipeline_tag == "image-text-to-text"):
            from_name.append(label)
        elif _hits(text, kws):
            from_text.append(label)
    uses = from_name + from_text
    if group == "llm":
        if re.search(r"(^|[-_])base($|[-_])", c.name.lower()) and "instruct" not in c.name.lower():
            uses.insert(0, "Base model (for fine-tuning)")
        if c.params_b is not None and c.params_b <= 4:
            uses.append("Small & fast")
    return uses[:3] or [DEFAULT_USE[group]]


def assign(cands: list[ModelCandidate], matrix: dict) -> None:
    for c in cands:
        c.good_for = good_for(c, matrix.get(c.repo_id))


def slug(repo_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", repo_id.replace("/", "__"))


def page_path(c: ModelCandidate) -> str:
    return f"models/{slug(c.repo_id)}.html"


def links(c: ModelCandidate) -> list[tuple[str, list[tuple[str, str]]]]:
    q = c.name.replace("-", " ").replace("_", " ")
    main = [("Hugging Face page" if c.source == "huggingface" else "GitHub repo", c.url)]
    if c.category == "llm":
        main += [("GGUF builds (LM Studio / llama.cpp)", f"https://huggingface.co/models?search={quote_plus(c.name)}+gguf"),
                 ("Ollama", f"https://ollama.com/search?q={quote_plus(q)}")]
        boards = [("LMArena leaderboard", "https://lmarena.ai/leaderboard"),
                  ("Artificial Analysis", "https://artificialanalysis.ai/models")]
        community = f"https://www.reddit.com/r/LocalLLaMA/search/?q={quote_plus(q)}"
    else:
        boards = []
        community = f"https://www.reddit.com/search/?q={quote_plus(q + ' music')}"
    reviews = [("YouTube reviews", f"https://www.youtube.com/results?search_query={quote_plus(q + ' review')}"),
               ("Reddit discussion", community),
               ("Web: benchmarks & reviews", f"https://www.google.com/search?q={quote_plus(q + ' benchmark review')}")]
    out = [("Get it", main), ("Reviews & discussion", reviews)]
    if boards:
        out.append(("Leaderboards (search for the model there)", boards))
    return out


def render(c: ModelCandidate, rating: dict | None, references: list[dict], today: str) -> str:
    e = html.escape
    group = c.category
    lic = c.license + (" (non-commercial)" if is_non_commercial(c.license) else "")
    size = "not published" if c.params_b is None else (
        f"{c.params_b:g}B parameters" + (f", {c.active_params_b:g}B active (MoE)" if c.active_params_b else
                                         " (MoE)" if c.is_moe else ""))
    pop = f"{c.stars:,} GitHub stars" if c.source == "github" else f"{c.likes:,} likes · {c.downloads:,} downloads"
    score = overall(rating)
    facts = [
        ("Good for", " · ".join(c.good_for) or DEFAULT_USE[group]),
        ("Runs on your machine?", f"<span class='fit {c.fit}'>{FIT_LABEL.get(c.fit, c.fit)}</span>"
                                  f"<small>{e(c.fit_detail)}</small>"),
        ("Overall rating", f"{score}/5 vs paid products" if score else "Not rated yet"),
        ("Size", size),
        ("Licence", e(lic) + (f"<small>{e(c.license_note)}</small>" if c.license_note else "")),
        ("Popularity", pop),
        ("Released / updated", f"{c.created or '?'} / {c.updated or '?'}"),
    ]
    if group == "llm":
        facts.append(("Quantised (GGUF) build", "Yes" if c.has_gguf else "Not yet"))

    body = [f"<p class='sub'><a href='../latest.html'>&larr; Back to this week's report</a></p>",
            f"<header><h1>{e(c.repo_id)}</h1><p class='sub'>{GROUP_TITLES[group].split(' vs ')[0]} &middot; "
            f"profile updated {today}</p></header>",
            "<div class='facts'>" + "".join(f"<div><span>{k}</span><b>{v}</b></div>" for k, v in facts) + "</div>"]

    what = c.summary or c.description
    body.append("<section><h2>What it is</h2>" +
                (f"<p>{e(what)}</p><p class='blurb'>From the model's own page.</p>" if what else
                 "<p class='empty'>The model page has no summary. Use the links below.</p>") + "</section>")

    body.append("<section><h2>Capability ratings</h2>")
    if rating and rating.get("scores"):
        best_ref = {}
        for ref in references:
            for d, v in ref.get("scores", {}).items():
                if v > best_ref.get(d, (0, ""))[0]:
                    best_ref[d] = (v, ref["name"])
        body.append(f"<p class='blurb'>{SCALE} Grey bar: best paid product in that area.</p><div class='bars'>")
        for d, label, desc in DIMENSIONS[group]:
            v = rating["scores"].get(d, 0)
            ref_v, ref_name = best_ref.get(d, (0, ""))
            body.append(
                f"<div class='bar' title='{e(desc)}'><span>{label}</span>"
                f"<div class='track'><i class='me s{v}' style='width:{v * 20}%'></i></div><b>{v or '&ndash;'}</b>"
                f"<div class='track ref'><i style='width:{ref_v * 20}%'></i></div>"
                f"<small title='{e(ref_name)}'>{'paid: ' + e(ref_name) + ' ' + str(ref_v) if ref_v else ''}</small></div>")
        body.append("</div>")
        body.append(f"<div class='proscons'><div><h3>Excels at</h3><p>{e(rating['excels'])}</p></div>"
                    f"<div><h3>Falls short</h3><p>{e(rating['falls_short'])}</p></div></div>")
        src = "".join(f"<li><a href='{e(u)}'>{e(u)}</a></li>" for u in rating.get("sources", []))
        body.append(f"<p class='blurb'>Confidence: {rating.get('confidence', 'low')}. Researched by Claude from "
                    f"public benchmarks and reviews.</p>" + (f"<ul class='src'>{src}</ul>" if src else ""))
    else:
        body.append("<p class='empty'>Not rated yet. Ratings against Claude, ChatGPT, Suno and other paid tools "
                    "are researched by Claude when ANTHROPIC_API_KEY is set in .env (the top models are rated, "
                    "and refreshed monthly).</p>")
    body.append("</section>")

    if c.benchmarks:
        rows = "".join(f"<tr><td>{e(b['benchmark'])}</td><td>{e(b['metric'])}</td><td>{b['value']:g}</td></tr>"
                       for b in c.benchmarks)
        body.append("<section><h2>Benchmarks published by the developer</h2><p class='blurb'>Self-reported on "
                    "the model card; not independently checked.</p><div class='scroll'><table><thead><tr>"
                    f"<th>Benchmark</th><th>Metric</th><th>Score</th></tr></thead><tbody>{rows}</tbody></table>"
                    "</div></section>")

    if c.mentions:
        items = "".join(f"<li><a href='{e(u)}'>{e(t)}</a></li>" for t, u in zip(c.mentions, c.mention_urls))
        body.append(f"<section><h2>In the news this week</h2><ul class='src'>{items}</ul></section>")

    for title, items in links(c):
        body.append(f"<section><h2>{title}</h2><ul class='src'>" +
                    "".join(f"<li><a href='{e(u)}'>{label}</a></li>" for label, u in items) + "</ul></section>")

    return HTML_TEMPLATE.replace("{{TITLE}}", e(c.name)).replace("{{BODY}}", "\n".join(body))
