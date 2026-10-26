"""News and chatter: YouTube, Reddit, Hacker News, arXiv.

These don't produce models directly; they surface what people are excited about
this week and boost the score of models that get mentioned.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import timezone

from .. import http
from ..models import NewsItem
from ..textutil import days_ago, is_music, since

log = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"
MEDIA = "{http://search.yahoo.com/mrss/}"
_CHANNEL_ID_RE = re.compile(r'"(?:channelId|externalId)":"(UC[\w-]{22})"')


def _topic(text: str) -> str:
    return "music" if is_music(text) else "llm"


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


# ---- YouTube ------------------------------------------------------------------

class YouTube:
    def __init__(self, cfg: dict, api_key: str, lookback_days: int, channel_cache: dict):
        self.cfg = cfg.get("youtube", {})
        self.api_key = api_key
        self.lookback = lookback_days
        self.cache = channel_cache  # handle -> UC id, persisted in state.json

    def resolve_channel(self, handle: str) -> str | None:
        if handle.startswith("UC"):
            return handle
        if handle in self.cache:
            return self.cache[handle]
        try:
            html = http.get(f"https://www.youtube.com/{handle}", headers={"Accept-Language": "en"}).decode(
                "utf-8", "replace")
        except http.FetchError as e:
            log.warning("Could not resolve YouTube channel %s: %s", handle, e)
            return None
        m = _CHANNEL_ID_RE.search(html)
        if m:
            self.cache[handle] = m.group(1)
            return m.group(1)
        return None

    def collect(self) -> list[NewsItem]:
        items = self._from_feeds()
        if self.api_key:
            items += self._from_search()
        return items

    def _from_feeds(self) -> list[NewsItem]:
        keywords = [k.lower() for k in self.cfg.get("title_keywords", [])]
        out = []
        for handle in self.cfg.get("channels", []):
            cid = self.resolve_channel(handle)
            if not cid:
                continue
            try:
                xml = http.get("https://www.youtube.com/feeds/videos.xml", {"channel_id": cid})
            except http.FetchError as e:
                log.warning("YouTube feed %s failed: %s", handle, e)
                continue
            out += [i for i in parse_youtube_feed(xml, self.lookback)
                    if not keywords or any(k in i.title.lower() for k in keywords)]
        return out

    def _from_search(self) -> list[NewsItem]:
        after = since(self.lookback).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out = []
        for q in self.cfg.get("searches", []):
            try:
                data = http.get_json("https://www.googleapis.com/youtube/v3/search", {
                    "part": "snippet", "q": q, "type": "video", "order": "viewCount",
                    "publishedAfter": after, "maxResults": 8, "relevanceLanguage": "en", "key": self.api_key})
            except http.FetchError as e:
                log.warning("YouTube search %r failed: %s", q, e)
                continue
            for it in data.get("items", []):
                sn = it.get("snippet", {})
                vid = it.get("id", {}).get("videoId")
                if not vid:
                    continue
                title = _strip_html(sn.get("title", ""))
                out.append(NewsItem(title=title, url=f"https://www.youtube.com/watch?v={vid}", source="youtube",
                                    channel=sn.get("channelTitle", ""), published=sn.get("publishedAt", "")[:10],
                                    summary=sn.get("description", "")[:300], topic=_topic(f"{q} {title}")))
        return out


def parse_youtube_feed(xml: bytes, lookback_days: int) -> list[NewsItem]:
    root = ET.fromstring(xml)
    channel = root.findtext(f"{ATOM}title", "")
    out = []
    for e in root.findall(f"{ATOM}entry"):
        published = e.findtext(f"{ATOM}published", "")
        if days_ago(published) > lookback_days:
            continue
        title = e.findtext(f"{ATOM}title", "")
        vid = e.findtext(f"{YT}videoId", "")
        desc = e.findtext(f"{MEDIA}group/{MEDIA}description", "") or ""
        out.append(NewsItem(title=title, url=f"https://www.youtube.com/watch?v={vid}", source="youtube",
                            channel=channel, published=published[:10], summary=desc[:300],
                            topic=_topic(title)))
    return out


# ---- Reddit -------------------------------------------------------------------

MUSIC_SUBS = {"aimusic", "wearethemusicmakers", "edmproduction", "musictheory"}


def collect_reddit(cfg: dict, lookback_days: int) -> list[NewsItem]:
    rc = cfg.get("reddit", {})
    music_kw = [k.lower() for k in rc.get("music_keywords", [])]
    out = []
    for sub in rc.get("subreddits", []):
        try:
            xml = http.get(f"https://www.reddit.com/r/{sub}/top/.rss", {"t": "week", "limit": 25})
        except http.FetchError as e:
            log.warning("Reddit r/%s failed: %s", sub, e)
            continue
        for item in parse_reddit_feed(xml, sub, lookback_days):
            if sub.lower() in MUSIC_SUBS:
                text = f"{item.title} {item.summary}".lower()
                if not any(k in text for k in music_kw):
                    continue
                item.topic = "music"
            out.append(item)
    return out


def parse_reddit_feed(xml: bytes, sub: str, lookback_days: int) -> list[NewsItem]:
    root = ET.fromstring(xml)
    out = []
    for e in root.findall(f"{ATOM}entry"):
        updated = e.findtext(f"{ATOM}updated", "") or e.findtext(f"{ATOM}published", "")
        if days_ago(updated) > lookback_days:
            continue
        link = e.find(f"{ATOM}link")
        title = e.findtext(f"{ATOM}title", "")
        summary = _strip_html(e.findtext(f"{ATOM}content", ""))[:300]
        out.append(NewsItem(title=title, url=link.get("href", "") if link is not None else "", source="reddit",
                            channel=f"r/{sub}", published=updated[:10], summary=summary,
                            topic=_topic(title)))
    return out


# ---- Hacker News ----------------------------------------------------------------

def collect_hackernews(cfg: dict, lookback_days: int) -> list[NewsItem]:
    after = int(since(lookback_days).timestamp())
    out, seen = [], set()
    for q in cfg.get("hackernews", {}).get("queries", []):
        try:
            data = http.get_json("https://hn.algolia.com/api/v1/search", {
                "query": q, "tags": "story", "numericFilters": f"created_at_i>{after},points>20",
                "hitsPerPage": 10})
        except http.FetchError as e:
            log.warning("Hacker News %r failed: %s", q, e)
            continue
        for h in data.get("hits", []):
            if h["objectID"] in seen:
                continue
            seen.add(h["objectID"])
            title = h.get("title") or ""
            out.append(NewsItem(title=title, url=h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                                source="hackernews", channel=f"{h.get('points', 0)} points",
                                published=(h.get("created_at") or "")[:10], topic=_topic(f"{q} {title}")))
    return out


# ---- arXiv ----------------------------------------------------------------------

def collect_arxiv(cfg: dict, lookback_days: int) -> list[NewsItem]:
    ac = cfg.get("arxiv", {})
    out, seen = [], set()
    for q in ac.get("queries", []):
        try:
            xml = http.get("https://export.arxiv.org/api/query", {
                "search_query": q, "sortBy": "submittedDate", "sortOrder": "descending",
                "max_results": ac.get("max_results", 15)})
        except http.FetchError as e:
            log.warning("arXiv %r failed: %s", q, e)
            continue
        for item in parse_arxiv_feed(xml, lookback_days):
            if item.url not in seen:
                seen.add(item.url)
                out.append(item)
    return out


def parse_arxiv_feed(xml: bytes, lookback_days: int) -> list[NewsItem]:
    root = ET.fromstring(xml)
    out = []
    for e in root.findall(f"{ATOM}entry"):
        published = e.findtext(f"{ATOM}published", "")
        if days_ago(published) > lookback_days:
            continue
        title = " ".join(e.findtext(f"{ATOM}title", "").split())
        summary = " ".join(e.findtext(f"{ATOM}summary", "").split())
        authors = [a.findtext(f"{ATOM}name", "") for a in e.findall(f"{ATOM}author")]
        out.append(NewsItem(title=title, url=e.findtext(f"{ATOM}id", ""), source="arxiv",
                            channel=", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
                            published=published[:10], summary=summary[:400], topic="music"))
    return out
