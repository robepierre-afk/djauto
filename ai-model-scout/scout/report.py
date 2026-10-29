"""Render the weekly report as Markdown, HTML and JSON."""

from __future__ import annotations

import html
import json
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .hardware import FIT_LABEL
from .models import ModelCandidate, NewsItem
from . import profile
from .page import HTML_TEMPLATE
from .ratings import DIMENSIONS, GROUP_TITLES, SCALE

MUSIC_SECTIONS = [
    ("music_generation", "Music generation", "Songs, instrumentals, vocals, samples and loops."),
    ("music_analysis", "Music analysis", "Stem separation, beats, chords, key, structure, tagging."),
    ("music_score", "Transcription & scores", "Audio to MIDI, sheet music, MusicXML, symbolic music."),
]
RUNS_HERE = ("gpu", "offload", "offload_slow")
SOURCE_LABEL = {"youtube": "YouTube", "reddit": "Reddit", "hackernews": "Hacker News", "arxiv": "arXiv"}


def _size(c: ModelCandidate) -> str:
    if c.params_b is None:
        return "?"
    s = f"{c.params_b:g}B" if c.params_b >= 1 else f"{c.params_b * 1000:.0f}M"
    return f"{s} ({c.active_params_b:g}B active)" if c.active_params_b else s


def _pop(c: ModelCandidate) -> str:
    return f"{c.stars:,} stars" if c.source == "github" else f"{c.likes:,} likes"


def _notes(c: ModelCandidate) -> str:
    bits = [c.fit_detail]
    if c.category == "llm":
        bits.append("GGUF available" if c.has_gguf else "no GGUF yet")
    if c.license_note:
        bits.append(c.license_note)
    if c.mentions:
        bits.append(f"in {len(c.mentions)} video/post(s) this week")
    if c.description:
        bits.insert(0, c.description[:140])
    return "; ".join(b for b in bits if b)


class Report:
    def __init__(self, machine: dict, llms: list[ModelCandidate], music: list[ModelCandidate],
                 news: list[NewsItem], briefing: str | None, errors: list[str], first_run: bool,
                 limits: dict, matrix: dict | None = None):
        self.machine = machine
        self.matrix = matrix or {}
        self.today = date.today().isoformat()
        # Everything worth knowing about, best first; the Fit column says whether it runs here.
        self.llms = llms[: limits.get("max_llms", 25)]
        self.runnable = [c for c in llms if c.fit in RUNS_HERE]
        self.music = {k: [c for c in music if c.category == k][: limits.get("max_music", 30) // 3 + 4]
                      for k, _, _ in MUSIC_SECTIONS}
        self.news = news[: limits.get("max_news", 40)]
        self.briefing = briefing
        self.errors = errors
        self.first_run = first_run
        self.all = llms + music
        self._by_id = {c.repo_id: c for c in self.all}

    @property
    def shown(self) -> list[ModelCandidate]:
        """Every model that appears in a table; each gets a profile page."""
        return self.llms + [c for rows in self.music.values() for c in rows]

    def _good_for(self, c: ModelCandidate) -> str:
        rating = profile.overall(self.matrix.get(c.repo_id))
        return " · ".join(c.good_for) + (f" (rated {rating}/5)" if rating else "")

    def matrix_rows(self, group: str) -> list[tuple[str, dict, ModelCandidate | None]]:
        """(display name, rating, candidate) for one group: paid references first, then by rank."""
        refs = sorted((r["name"], r, None) for r in self.matrix.values()
                      if r["group"] == group and r.get("is_reference"))
        ranked = [c for c in self.all if c.repo_id in self.matrix and self.matrix[c.repo_id]["group"] == group]
        return refs + [(c.repo_id, self.matrix[c.repo_id], c) for c in ranked]

    @property
    def new_count(self) -> int:
        return 0 if self.first_run else sum(c.is_new for c in self.all)

    def headline(self) -> list[str]:
        """Short lines for the Telegram notification."""
        lines = []
        new = [c for c in self.llms + [m for v in self.music.values() for m in v] if c.is_new]
        if new and not self.first_run:
            lines.append("New this week: " + ", ".join(c.repo_id for c in new[:6]))
        if self.llms:
            lines.append("Top open LLMs: " + ", ".join(
                c.name + ("" if c.fit in RUNS_HERE else " (too big here)") for c in self.llms[:3]))
        if self.runnable:
            lines.append("Best that run on your machine: " + ", ".join(c.name for c in self.runnable[:3]))
        for key, title, _ in MUSIC_SECTIONS:
            if self.music[key]:
                lines.append(f"{title}: " + ", ".join(c.name for c in self.music[key][:3]))
        return lines

    # ---- Markdown -----------------------------------------------------------
    def markdown(self) -> str:
        m = self.machine
        out = [f"# AI Model Scout: {self.today}", "",
               f"Machine: **{m.get('name', '')}**, {m.get('gpu_vram_gb')} GB VRAM, {m.get('system_ram_gb')} GB RAM. "
               "Only models with free, downloadable weights are listed. **NEW** = first seen this week.", ""]
        if self.briefing:
            out += ["## Weekly briefing", "", self.briefing, ""]
        out += self._md_matrix()
        out += self._md_table("Top open LLMs", self.llms,
                              blurb="Ranked best first, whatever their size. "
                                    "'Runs here?' says whether your machine can run each one.")
        for key, title, blurb in MUSIC_SECTIONS:
            out += self._md_table(title, self.music[key], blurb=blurb)
        out += ["## This week's videos and discussions", ""]
        for topic, label in (("llm", "LLMs"), ("music", "Music AI")):
            items = [n for n in self.news if n.topic == topic]
            if items:
                out += [f"### {label}", ""]
                out += [f"- [{n.title}]({n.url}): {SOURCE_LABEL.get(n.source, n.source)}, {n.channel}, {n.published}"
                        for n in items]
                out.append("")
        if self.errors:
            out += ["## Sources that failed this run", ""] + [f"- {e}" for e in self.errors] + [""]
        return "\n".join(out)

    def _md_matrix(self) -> list[str]:
        if not self.matrix:
            return []
        out = ["## Industry rating matrix", "", f"Scores per capability. {SCALE} Paid products are shown "
               "first for comparison.", ""]
        for group, dims in DIMENSIONS.items():
            rows = self.matrix_rows(group)
            if not rows:
                continue
            out += [f"### {GROUP_TITLES[group]}", "",
                    "| Model | Runs here? | " + " | ".join(label for _, label, _ in dims) + " | Excels at | Falls short |",
                    "|---|---|" + "---|" * len(dims) + "---|---|"]
            for name, r, c in rows:
                label = f"**{name}** (paid)" if c is None else f"[{name}]({c.url})"
                fit = "n/a" if c is None else FIT_LABEL.get(c.fit, c.fit)
                cells = [str(r["scores"].get(d) or "–") for d, _, _ in dims]
                out.append(f"| {label} | {fit} | " + " | ".join(cells) +
                           f" | {r['excels'].replace('|', '/')} | {r['falls_short'].replace('|', '/')} |")
            out.append("")
        return out

    def _md_table(self, title: str, rows: list[ModelCandidate], llm: bool = False, blurb: str = "") -> list[str]:
        out = [f"## {title}", ""]
        if blurb:
            out += [blurb, ""]
        if not rows:
            return out + ["_Nothing found this week._", ""]
        out += ["| Model | Good for | Size | Runs here? | Licence | Popularity | Notes |",
                "|---|---|---|---|---|---|---|"]
        for c in rows:
            name = (f"[{c.repo_id}]({profile.page_path(c)})" + (" **NEW**" if c.is_new and not self.first_run else ""))
            notes = _notes(c).replace("|", "/")
            out.append(f"| {name} | {self._good_for(c)} | {_size(c)} | {FIT_LABEL.get(c.fit, c.fit)} | {c.license} "
                       f"| {_pop(c)} | {notes} |")
        return out + [""]

    # ---- HTML -------------------------------------------------------------------
    def html(self) -> str:
        m = self.machine
        body = [f"<header><h1>AI Model Scout</h1><p class='sub'>{self.today} &middot; "
                f"{html.escape(str(m.get('name', '')))}: {m.get('gpu_vram_gb')} GB VRAM, {m.get('system_ram_gb')} GB RAM"
                f" &middot; open, downloadable weights only</p></header>"]
        stats = [("Top LLMs that run here", f"{sum(c.fit in RUNS_HERE for c in self.llms)} of {len(self.llms)}"),
                 ("Music models", sum(len(v) for v in self.music.values())),
                 ("New this week", self.new_count), ("Videos & posts", len(self.news))]
        body.append("<div class='stats'>" + "".join(
            f"<div class='stat'><b>{v}</b><span>{k}</span></div>" for k, v in stats) + "</div>")
        if self.briefing:
            body.append(f"<section class='brief'><h2>Weekly briefing</h2>{md_to_html(self.briefing)}</section>")
        body.append("<label class='filter'><input type='checkbox' id='onlyhere'> "
                    "Only show models that run on my machine</label>")
        body.append(self._html_matrix())
        body.append(self._html_table("Top open LLMs", self.llms,
                                     "Ranked best first, whatever their size. "
                                     "'Runs here?' says whether your machine can run each one."))
        for key, title, blurb in MUSIC_SECTIONS:
            body.append(self._html_table(title, self.music[key], blurb))
        body.append("<section><h2>This week's videos and discussions</h2>")
        for topic, label in (("llm", "LLMs"), ("music", "Music AI")):
            items = [n for n in self.news if n.topic == topic]
            if items:
                body.append(f"<h3>{label}</h3><ul class='news'>")
                for n in items:
                    body.append(f"<li><span class='src {n.source}'>{SOURCE_LABEL.get(n.source, n.source)}</span>"
                                f"<a href='{html.escape(n.url)}'>{html.escape(n.title)}</a>"
                                f"<small>{html.escape(n.channel)} &middot; {n.published}</small></li>")
                body.append("</ul>")
        body.append("</section>")
        if self.errors:
            body.append("<section><h2>Sources that failed this run</h2><ul>" +
                        "".join(f"<li>{html.escape(e)}</li>" for e in self.errors) + "</ul></section>")
        return HTML_TEMPLATE.replace("{{TITLE}}", f"AI Model Scout {self.today}").replace("{{BODY}}", "\n".join(body))

    def _html_matrix(self) -> str:
        if not self.matrix:
            return ""
        h = ["<section><h2>Industry rating matrix</h2>",
             f"<p class='blurb'>Scores per capability, researched from benchmarks and reviews. {SCALE} "
             "Paid products are shown first for comparison. Hover a column heading for what it measures.</p>"]
        for group, dims in DIMENSIONS.items():
            rows = self.matrix_rows(group)
            if not rows:
                continue
            h.append(f"<h3>{GROUP_TITLES[group]}</h3><div class='scroll'><table class='matrix'><thead><tr>"
                     "<th>Model</th><th>Runs here?</th>" +
                     "".join(f"<th title='{html.escape(desc)}'>{label}</th>" for _, label, desc in dims) +
                     "<th>Excels at</th><th>Falls short</th></tr></thead><tbody>")
            for name, r, c in rows:
                if c is None:
                    head = f"<b>{html.escape(name)}</b><small>paid reference</small>"
                    fit, fit_cls = "n/a", "check"
                else:
                    head = f"<a href='{profile.page_path(c)}'>{html.escape(name)}</a>"
                    fit, fit_cls = FIT_LABEL.get(c.fit, c.fit), c.fit
                links = " ".join(f"<a href='{html.escape(u)}'>[{i}]</a>" for i, u in enumerate(r["sources"], 1))
                head += f"<small>confidence: {r['confidence']}{' &middot; ' + links if links else ''}</small>"
                cells = "".join(
                    f"<td class='score s{r['scores'].get(d, 0)}'>{r['scores'].get(d) or '&ndash;'}</td>"
                    for d, _, _ in dims)
                h.append(f"<tr class='{'ref' if c is None else ''}' data-fit='{c.fit if c else 'ref'}'>"
                         f"<td>{head}</td><td><span class='fit {fit_cls}'>{fit}</span></td>{cells}"
                         f"<td class='notes'>{html.escape(r['excels'])}</td>"
                         f"<td class='notes'>{html.escape(r['falls_short'])}</td></tr>")
            h.append("</tbody></table></div>")
        return "".join(h) + "</section>"

    def _html_table(self, title: str, rows: list[ModelCandidate], blurb: str = "") -> str:
        h = [f"<section><h2>{title}</h2>"]
        if blurb:
            h.append(f"<p class='blurb'>{blurb}</p>")
        if not rows:
            return "".join(h) + "<p class='empty'>Nothing found this week.</p></section>"
        h.append("<div class='scroll'><table><thead><tr><th>Model</th><th>Good for</th><th>Size</th><th>Runs here?</th>"
                 "<th>Licence</th><th>Popularity</th><th>Notes</th></tr></thead><tbody>")
        for c in rows:
            badge = "<span class='new'>NEW</span>" if c.is_new and not self.first_run else ""
            rating = profile.overall(self.matrix.get(c.repo_id))
            h.append(f"<tr data-fit='{c.fit}'><td><a href='{profile.page_path(c)}'>{html.escape(c.repo_id)}</a>{badge}"
                     f"<small>{c.updated or c.created} &middot; <a class='profile-link' "
                     f"href='{profile.page_path(c)}'>profile &amp; ratings &rarr;</a></small></td>"
                     f"<td class='goodfor'>{html.escape(' · '.join(c.good_for))}"
                     f"{f'<small>rated {rating}/5 vs paid</small>' if rating else ''}</td><td>{_size(c)}</td>"
                     f"<td><span class='fit {c.fit}'>{FIT_LABEL.get(c.fit, c.fit)}</span></td>"
                     f"<td>{html.escape(c.license)}</td><td>{_pop(c)}</td>"
                     f"<td class='notes'>{html.escape(_notes(c))}</td></tr>")
        return "".join(h) + "</tbody></table></div></section>"

    # ---- Write ------------------------------------------------------------------
    def write(self, out_dir: Path) -> dict[str, Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = {"md": out_dir / f"{self.today}.md", "html": out_dir / f"{self.today}.html",
                 "json": out_dir / f"{self.today}.json"}
        paths["md"].write_text(self.markdown(), encoding="utf-8")
        paths["html"].write_text(self.html(), encoding="utf-8")
        paths["json"].write_text(json.dumps({
            "date": self.today, "machine": self.machine, "briefing": self.briefing,
            "models": [asdict(c) for c in self.all], "ratings": self.matrix, "news": [asdict(n) for n in self.news],
            "errors": self.errors}, indent=1), encoding="utf-8")
        (out_dir / "latest.html").write_text(self.html(), encoding="utf-8")
        (out_dir / "models").mkdir(exist_ok=True)
        refs = [r for r in self.matrix.values() if r.get("is_reference")]
        for c in self.shown:
            page = profile.render(c, self.matrix.get(c.repo_id), [r for r in refs if r["group"] == c.category],
                                  self.today)
            (out_dir / profile.page_path(c)).write_text(page, encoding="utf-8")
        return paths


def md_to_html(md: str) -> str:
    """Just enough Markdown for the briefing: headings, bullets, bold, italics, links, paragraphs."""
    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<a href='\2'>\1</a>", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", s)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)

    out, in_list, para = [], False, []

    def flush():
        nonlocal in_list
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in md.splitlines():
        s = line.strip()
        if not s:
            flush()
        elif m := re.match(r"(#{1,6})\s+(.*)", s):
            flush()
            lvl = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
        elif m := re.match(r"[-*]\s+(.*)|\d+\.\s+(.*)", s):
            if para:
                out.append(f"<p>{inline(' '.join(para))}</p>")
                para.clear()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(m.group(1) or m.group(2))}</li>")
        else:
            if in_list:
                flush()
            para.append(s)
    flush()
    return "\n".join(out)
