"""End-to-end run with every network call answered by canned responses."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

from scout import __main__ as app
from scout import http
from scout.config import load_config


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def hf_row(rid, pipeline="text-generation", likes=100, trending=10, created=3, params=None, tags=(), **kw):
    row = {"id": rid, "likes": likes, "downloads": likes * 50, "trendingScore": trending,
           "createdAt": ago(created), "lastModified": ago(created), "pipeline_tag": pipeline,
           "tags": list(tags), "gated": False, "cardData": {"license": kw.get("license", "apache-2.0")}}
    if "model_type" in kw:
        row["config"] = {"model_type": kw["model_type"]}
    if params:
        row["safetensors"] = {"total": int(params * 1e9)}
    return row


HF_LLM = [
    hf_row("Qwen/Qwen4-32B", likes=900, trending=400, params=32.8),
    hf_row("Qwen/Qwen4-235B-A22B", likes=1500, trending=600, params=235),
    hf_row("deepseek-ai/DeepSeek-V4", likes=3000, trending=900, params=685),
    hf_row("openai/gpt-oss-120b", likes=4000, trending=200, created=200, params=120.4, model_type="gpt_oss"),
    hf_row("unsloth/Qwen4-32B-GGUF", tags=["gguf", "base_model:quantized:Qwen/Qwen4-32B"]),
    hf_row("google/gemma-4-12b-it", pipeline="image-text-to-text", likes=700, trending=150, license="gemma"),
    hf_row("someone/old-model-7B", created=900),
    hf_row("someone/embedder", pipeline="feature-extraction"),
]
HF_MUSIC = [
    hf_row("ACE-Step/ACE-Step-v1-3.5B", pipeline="text-to-audio", likes=800, created=120,
           tags=["music", "text-to-music"]),
    hf_row("facebook/musicgen-large", pipeline="text-to-audio", likes=500, created=300,
           tags=["musicgen", "audiocraft"], license="cc-by-nc-4.0"),
    hf_row("newlab/SongMaker-2B", pipeline="text-to-audio", likes=60, trending=80, created=4,
           tags=["music", "song-generation"]),
    hf_row("tts/voice-only", pipeline="text-to-speech", tags=["tts"]),
]
GH_SEARCH = {"items": [
    {"full_name": "spotify/basic-pitch", "html_url": "https://github.com/spotify/basic-pitch",
     "description": "Audio-to-MIDI transcription", "topics": ["music-transcription", "midi"],
     "stargazers_count": 4000, "created_at": ago(1500), "pushed_at": ago(20), "license": {"spdx_id": "Apache-2.0"}},
    {"full_name": "facebookresearch/demucs", "html_url": "https://github.com/facebookresearch/demucs",
     "description": "Music source separation", "topics": ["source-separation"],
     "stargazers_count": 9000, "created_at": ago(1800), "pushed_at": ago(100), "license": {"spdx_id": "MIT"}},
]}


def yt_feed():
    return f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"
 xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/">
<title>Matthew Berman</title>
<entry><yt:videoId>abc</yt:videoId><title>Qwen4 235B is the best open source model yet</title>
<published>{ago(2)}</published><media:group><media:description>local test</media:description></media:group></entry>
<entry><yt:videoId>def</yt:videoId><title>My cat video</title><published>{ago(1)}</published></entry>
<entry><yt:videoId>old</yt:videoId><title>Old open source news</title><published>{ago(60)}</published></entry>
</feed>""".encode()


def reddit_feed():
    return f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>DeepSeek-V4 GGUF is out, running it with 64GB RAM</title><link href="https://reddit.com/r/x/1"/>
<updated>{ago(3)}</updated><content>&lt;p&gt;benchmarks inside&lt;/p&gt;</content></entry>
<entry><title>SongMaker open weights song generation model released</title><link href="https://reddit.com/r/x/2"/>
<updated>{ago(2)}</updated><content>github link</content></entry>
</feed>""".encode()


def arxiv_feed():
    return f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/abs/2610.00001</id><title>Fast   Full-Song
Generation</title><summary>We present...</summary><published>{ago(5)}</published>
<author><name>A</name></author><author><name>B</name></author></entry></feed>""".encode()


def fake_get(url, params=None, headers=None, **kw):
    u = urlparse(url)
    p = {}
    if isinstance(params, dict):
        p = {k: str(v) for k, v in params.items()}
    elif isinstance(params, list):
        for k, v in params:
            p.setdefault(k, str(v))
    if u.netloc == "huggingface.co":
        if "filter" in p:
            return json.dumps([]).encode()
        if p.get("pipeline_tag") in ("text-generation", "image-text-to-text") or "author" in p and "search" not in p:
            return json.dumps(HF_LLM).encode()
        return json.dumps(HF_MUSIC).encode()
    if u.netloc == "api.github.com":
        if u.path.startswith("/search"):
            return json.dumps(GH_SEARCH).encode()
        name = u.path.removeprefix("/repos/")
        return json.dumps({**GH_SEARCH["items"][0], "full_name": name,
                           "html_url": f"https://github.com/{name}", "description": "music analysis"}).encode()
    if u.netloc == "www.youtube.com" and u.path.startswith("/@"):
        return b'<html>"channelId":"UCawZsQWqfGSbCI5yjkdVkTA"</html>'
    if u.path == "/feeds/videos.xml":
        return yt_feed()
    if u.netloc == "www.reddit.com":
        return reddit_feed()
    if u.netloc == "hn.algolia.com":
        return json.dumps({"hits": [{"objectID": "1", "title": "Open weights model tops leaderboard",
                                     "url": "https://x.y", "points": 300, "created_at": ago(1)}]}).encode()
    if u.netloc == "export.arxiv.org":
        return arxiv_feed()
    raise http.FetchError(f"unexpected {url}")


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = load_config()
        self.cfg["report"]["output_dir"] = self.tmp.name
        # Fixed test machine, independent of whatever the example config ships with.
        self.cfg["machine"] = {"name": "Test rig", "gpu_vram_gb": 24, "system_ram_gb": 64}
        self.cfg["secrets"] = {k: "" for k in self.cfg["secrets"]}
        self.sent = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_once(self):
        with mock.patch.object(http, "get", side_effect=fake_get), \
                mock.patch.object(http.time, "sleep"), \
                mock.patch.object(http, "post_json", side_effect=lambda *a, **k: self.sent.append(a)):
            return app.run(self.cfg, use_analyst=False)

    def test_full_run(self):
        report, paths = self.run_once()
        fits = {c.repo_id: c.fit for c in report.llms}
        self.assertEqual(fits["Qwen/Qwen4-32B"], "gpu")
        self.assertEqual(fits["openai/gpt-oss-120b"], "offload")    # MoE (from config) -> usable with offload
        self.assertEqual(fits["Qwen/Qwen4-235B-A22B"], "too_big")   # listed anyway, flagged as too big
        self.assertEqual(fits["deepseek-ai/DeepSeek-V4"], "too_big")
        self.assertNotIn("someone/old-model-7B", fits)              # too old
        self.assertNotIn("unsloth/Qwen4-32B-GGUF", fits)            # quant folded into base
        self.assertNotIn("Qwen/Qwen4-235B-A22B", [c.repo_id for c in report.runnable])
        qwen = next(c for c in report.llms if c.repo_id == "Qwen/Qwen4-32B")
        self.assertTrue(qwen.has_gguf)
        ds = next(c for c in report.llms if c.repo_id.endswith("DeepSeek-V4"))
        self.assertTrue(ds.mentions)                                # linked to the Reddit post

        music_ids = {c.repo_id for v in report.music.values() for c in v}
        self.assertIn("ACE-Step/ACE-Step-v1-3.5B", music_ids)
        self.assertIn("spotify/basic-pitch", music_ids)
        self.assertNotIn("tts/voice-only", music_ids)
        self.assertIn("spotify/basic-pitch", [c.repo_id for c in report.music["music_score"]])
        self.assertIn("facebookresearch/demucs", [c.repo_id for c in report.music["music_analysis"]])
        mg = next(c for c in report.music["music_generation"] if c.repo_id == "facebook/musicgen-large")
        self.assertIn("non-commercial", mg.license_note)

        titles = [n.title for n in report.news]
        self.assertIn("Qwen4 235B is the best open source model yet", titles)
        self.assertNotIn("My cat video", titles)
        self.assertNotIn("Old open source news", titles)
        self.assertIn("Fast Full-Song Generation", titles)
        self.assertEqual(len(titles), len(set(n.url for n in report.news)))  # de-duplicated

        for key in ("md", "html", "json"):
            self.assertTrue(paths[key].exists())
        html = paths["html"].read_text()
        self.assertIn("Qwen/Qwen4-32B", html)
        self.assertIn("<tr data-fit='too_big'>", html)
        self.assertIn("No, too big", html)
        self.assertIn("id='onlyhere'", html)
        self.assertNotIn("<span class='new'>", html)            # first run: nothing flagged NEW
        self.assertEqual(report.errors, [])
        self.assertTrue((Path(self.tmp.name) / "state.json").exists())

    def test_second_run_flags_new(self):
        self.run_once()
        HF_MUSIC.append(hf_row("brandnew/Music-1B", pipeline="text-to-audio", likes=5, created=1,
                               tags=["music"]))
        try:
            report, paths = self.run_once()
        finally:
            HF_MUSIC.pop()
        new = [c.repo_id for c in report.all if c.is_new]
        self.assertEqual(new, ["brandnew/Music-1B"])
        self.assertIn("<span class='new'>NEW</span>", paths["html"].read_text())

    def test_failed_source_is_reported_not_fatal(self):
        def flaky(url, *a, **k):
            if "reddit" in url:
                raise http.FetchError("403")
            return fake_get(url, *a, **k)
        with mock.patch.object(http, "get", side_effect=flaky), mock.patch.object(http.time, "sleep"):
            report, _ = app.run(self.cfg, use_analyst=False)
        self.assertTrue(any(e.startswith("Reddit") for e in report.errors))
        self.assertTrue(report.llms)

    def test_rejected_github_token_falls_back_to_anonymous(self):
        self.cfg["secrets"]["GITHUB_TOKEN"] = "bad"

        def strict(url, params=None, headers=None, **k):
            if "api.github.com" in url and "Authorization" in (headers or {}):
                raise http.FetchError(f"GET {url} failed: HTTP Error 401: Unauthorized")
            return fake_get(url, params, headers, **k)
        with mock.patch.object(http, "get", side_effect=strict), mock.patch.object(http.time, "sleep"):
            report, _ = app.run(self.cfg, use_analyst=False)
        self.assertIn("spotify/basic-pitch", [c.repo_id for c in report.music["music_score"]])

    def test_github_failure_reason_is_reported(self):
        def no_github(url, *a, **k):
            if "api.github.com" in url:
                raise http.FetchError(f"GET {url} failed: HTTP Error 403: rate limit exceeded")
            return fake_get(url, *a, **k)
        with mock.patch.object(http, "get", side_effect=no_github), mock.patch.object(http.time, "sleep"):
            report, _ = app.run(self.cfg, use_analyst=False)
        gh = [e for e in report.errors if e.startswith("GitHub music")]
        self.assertEqual(len(gh), 1)
        self.assertIn("403: rate limit exceeded", gh[0])

    def test_telegram_sent_when_configured(self):
        self.cfg["secrets"].update(TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_ID="1")
        self.run_once()
        self.assertEqual(len(self.sent), 1)
        text = self.sent[0][1]["text"]
        self.assertIn("Top open LLMs:", text)
        self.assertIn("(too big here)", text)
        self.assertIn("Best that run on your machine:", text)


if __name__ == "__main__":
    unittest.main()
