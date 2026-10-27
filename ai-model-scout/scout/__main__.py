"""Entry point: python -m scout [--config path] [--no-analyst] [--open]"""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from pathlib import Path

from . import analyst, hardware, http, notify, scoring
from .config import APP_DIR, load_config
from .models import ModelCandidate, NewsItem
from .report import Report
from .sources import news as news_src
from .sources.github import GitHub
from .sources.huggingface import HuggingFace
from .state import State
from .watchlist import MUSIC_GITHUB, MUSIC_HF

log = logging.getLogger("scout")


def run(cfg: dict, use_analyst: bool = True) -> tuple[Report, dict]:
    secrets = cfg["secrets"]
    rcfg = cfg.get("report", {})
    lookback = int(rcfg.get("lookback_days", 14))
    machine = cfg.get("machine", {})
    out_dir = (APP_DIR / rcfg.get("output_dir", "reports")).resolve()
    state = State(out_dir / "state.json")
    errors: list[str] = []

    def guarded(label, fn, default):
        log.info("Collecting: %s", label)
        try:
            result = fn()
        except http.FetchError as e:
            log.warning("%s failed: %s", label, e)
            errors.append(f"{label}: {e}")
            return default
        except Exception as e:  # one broken source must not sink the weekly report
            log.exception("%s failed", label)
            errors.append(f"{label}: {e}")
            return default
        if not result:
            errors.append(f"{label}: returned nothing (blocked, rate-limited or offline?)")
        return result

    hf = HuggingFace(cfg, secrets.get("HF_TOKEN", ""))
    gh = GitHub(cfg, secrets.get("GITHUB_TOKEN", ""), lookback)
    yt = news_src.YouTube(cfg, secrets.get("YOUTUBE_API_KEY", ""), lookback, state.channel_cache)

    llms: list[ModelCandidate] = guarded("Hugging Face LLMs", hf.collect_llms, [])
    music: list[ModelCandidate] = guarded("Hugging Face music", lambda: hf.collect_music(MUSIC_HF), [])
    music += guarded("GitHub music", lambda: gh.collect_music(MUSIC_GITHUB), [])

    news: list[NewsItem] = []
    news += guarded("YouTube", yt.collect, [])
    news += guarded("Reddit", lambda: news_src.collect_reddit(cfg, lookback), [])
    news += guarded("Hacker News", lambda: news_src.collect_hackernews(cfg, lookback), [])
    news += guarded("arXiv", lambda: news_src.collect_arxiv(cfg, lookback), [])
    # The same video/post can arrive via several feeds and searches.
    news = list({n.url: n for n in news}.values())
    news.sort(key=lambda n: n.published, reverse=True)

    for c in llms + music:
        hardware.assess(c, machine)
    scoring.attach_mentions(llms + music, news)
    llms = scoring.rank(llms, lookback)
    music = scoring.rank(music, lookback)

    if rcfg.get("hide_gated"):
        llms = [c for c in llms if not c.gated]
        music = [c for c in music if not c.gated]
    if rcfg.get("hide_non_commercial"):
        music = [c for c in music if "non-commercial" not in c.license_note]
        llms = [c for c in llms if "non-commercial" not in c.license_note]

    # Only spend GGUF lookups on the LLMs that will actually be shown.
    hf.check_gguf([c for c in llms if c.fit in ("gpu", "offload")][: rcfg.get("max_llms", 25)])

    first_run = state.first_run
    new_ids = state.mark([c.repo_id for c in llms + music])
    for c in llms + music:
        c.is_new = c.repo_id in new_ids

    briefing = None
    if use_analyst:
        log.info("Writing briefing with Claude")
        briefing = analyst.write_briefing(cfg, machine, llms, music, news)

    report = Report(machine, llms, music, news, briefing, errors, first_run, rcfg)
    paths = report.write(out_dir)
    state.save(str(paths["html"]))

    if cfg.get("notify", {}).get("telegram", True):
        notify.telegram(secrets.get("TELEGRAM_BOT_TOKEN", ""), secrets.get("TELEGRAM_CHAT_ID", ""),
                        report.headline(), str(paths["html"]))
    return report, paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scout", description="Weekly scan for open-weight LLMs and music AI models.")
    ap.add_argument("--config", help="path to config.toml (default: config.toml, then config.example.toml)")
    ap.add_argument("--no-analyst", action="store_true", help="skip the Claude-written briefing")
    ap.add_argument("--open", action="store_true", help="open the HTML report when done")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    cfg = load_config(args.config)
    log.info("Using config %s", cfg["_path"])
    report, paths = run(cfg, use_analyst=not args.no_analyst)
    print(f"\nReport written:\n  {paths['html']}\n  {paths['md']}")
    for line in report.headline():
        print(" -", line)
    if report.errors:
        print("\nSome sources failed (see the report):")
        for e in report.errors:
            print(" -", e)
    if args.open:
        webbrowser.open(Path(paths["html"]).as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
