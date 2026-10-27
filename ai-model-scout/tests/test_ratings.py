import json
import unittest
from datetime import date, timedelta
from unittest import mock

from scout import ratings
from scout.models import ModelCandidate
from scout.report import Report


def cand(rid, category="llm", fit="gpu"):
    return ModelCandidate(repo_id=rid, category=category, source="huggingface",
                          url=f"https://huggingface.co/{rid}", fit=fit)


LLMS = [cand("Qwen/Qwen4-32B"), cand("deepseek-ai/DeepSeek-V4", fit="too_big")]
MUSIC = [cand("ACE-Step/ACE-Step-v1-3.5B", "music_generation", "offload")]
CFG = {"secrets": {"ANTHROPIC_API_KEY": "k"}, "analyst": {}, "ratings": {}}

STRUCTURED = {"ratings": [
    {"id": "Qwen/Qwen4-32B", "group": "llm", "is_reference": False,
     "scores": [{"area": "coding", "score": 4}, {"area": "vision", "score": 0}, {"area": "vocals", "score": 5},
                {"area": "reasoning", "score": 9}],
     "excels": "Strong coder for its size.", "falls_short": "Weaker long-context recall.",
     "confidence": "medium", "sources": ["https://example.com/bench", "not-a-url"]},
    {"id": "DeepSeek-V4", "group": "llm", "is_reference": False, "scores": [], "excels": "", "falls_short": "",
     "confidence": "low", "sources": []},  # id doesn't match a requested repo: dropped
    {"id": "Claude (latest)", "group": "llm", "is_reference": True,
     "scores": [{"area": "coding", "score": 5}], "excels": "Best coder.", "falls_short": "Paid only.",
     "confidence": "high", "sources": []},
    {"id": "ACE-Step/ACE-Step-v1-3.5B", "group": "music_generation", "is_reference": False,
     "scores": [{"area": "vocals", "score": 3}], "excels": "Full songs fast.", "falls_short": "Vocals less clear.",
     "confidence": "medium", "sources": []},
]}


class Ratings(unittest.TestCase):
    def run_rate(self, cache, notes="notes", structured=STRUCTURED):
        calls = []

        def fake_ask(client, cfg, purpose, system, messages, **kw):
            calls.append((purpose, kw))
            return notes if purpose == "rating research" else json.dumps(structured)
        with mock.patch.object(ratings, "claude_client", return_value=object()), \
                mock.patch.object(ratings, "ask_claude", side_effect=fake_ask):
            out = ratings.rate(CFG, cache, LLMS, MUSIC)
        return out, calls

    def test_two_step_research_then_structure(self):
        cache = {}
        out, calls = self.run_rate(cache)
        self.assertEqual([c[0] for c in calls], ["rating research", "rating matrix"])
        self.assertIn("web_searches", calls[0][1])           # research searches the web
        self.assertNotIn("web_searches", calls[1][1])        # structuring has no tools (citations clash)
        self.assertIn("json_schema", calls[1][1])
        q = out["Qwen/Qwen4-32B"]
        self.assertEqual(q["scores"], {"coding": 4, "vision": 0, "reasoning": 5})  # clamped, foreign area dropped
        self.assertEqual(q["sources"], ["https://example.com/bench"])
        self.assertIn("ref:llm:Claude (latest)", out)
        self.assertNotIn("DeepSeek-V4", out)
        self.assertTrue(all("rated" in v for v in cache.values()))

    def test_fresh_cache_skips_claude(self):
        today = date.today().isoformat()
        cache = {"Qwen/Qwen4-32B": {"group": "llm", "rated": today, "scores": {}},
                 "deepseek-ai/DeepSeek-V4": {"group": "llm", "rated": today, "scores": {}},
                 "ACE-Step/ACE-Step-v1-3.5B": {"group": "music_generation", "rated": today, "scores": {}}}
        out, calls = self.run_rate(cache)
        self.assertEqual(calls, [])
        self.assertEqual(set(out), set(cache))

    def test_stale_entries_are_refreshed(self):
        old = (date.today() - timedelta(days=45)).isoformat()
        cache = {"Qwen/Qwen4-32B": {"group": "llm", "rated": old, "scores": {}}}
        _, calls = self.run_rate(cache)
        self.assertTrue(calls)
        self.assertEqual(cache["Qwen/Qwen4-32B"]["scores"]["coding"], 4)

    def test_failed_research_leaves_cache_alone(self):
        cache = {}
        out, calls = self.run_rate(cache, notes=None)
        self.assertEqual([c[0] for c in calls], ["rating research"])
        self.assertEqual(out, {})

    def test_without_api_key_nothing_happens(self):
        out = ratings.rate({"secrets": {}, "analyst": {}}, {}, LLMS, MUSIC)
        self.assertEqual(out, {})

    def test_report_renders_matrix(self):
        cache = {}
        matrix, _ = self.run_rate(cache)
        rep = Report({"name": "m", "gpu_vram_gb": 8, "system_ram_gb": 32}, LLMS, MUSIC, [], None, [], True,
                     {}, matrix)
        html = rep.html()
        self.assertIn("Industry rating matrix", html)
        self.assertIn("Open LLMs vs Claude / ChatGPT / Gemini", html)
        self.assertIn("<td class='score s4'>4</td>", html)
        self.assertIn("paid reference", html)
        self.assertIn("Music generation vs paid tools", html)
        self.assertLess(html.index("Claude (latest)"), html.index("Qwen/Qwen4-32B</a><small>confidence"))
        md = rep.markdown()
        self.assertIn("| **Claude (latest)** (paid) | n/a | 5 |", md)


if __name__ == "__main__":
    unittest.main()
