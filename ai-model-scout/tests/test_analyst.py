import unittest
from types import SimpleNamespace
from unittest import mock

from scout import analyst

try:
    import anthropic
except ImportError:  # the briefing is optional, and so is its SDK
    anthropic = None

CFG = {"analyst": {"enabled": True}, "secrets": {"ANTHROPIC_API_KEY": "k"}}


def msg(stop, text=""):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


@unittest.skipIf(anthropic is None, "anthropic not installed")
class Analyst(unittest.TestCase):
    def run_with(self, responses):
        calls = []

        def stream(**kw):
            calls.append(kw)
            cm = mock.MagicMock()
            cm.__enter__.return_value.get_final_message.return_value = responses[len(calls) - 1]
            return cm

        client = mock.MagicMock()
        client.beta.messages.stream.side_effect = stream
        with mock.patch.object(anthropic, "Anthropic", return_value=client):
            out = analyst.write_briefing(CFG, {}, [], [], [])
        return out, calls

    def test_resumes_after_pause_turn(self):
        out, calls = self.run_with([msg("pause_turn"), msg("end_turn", "## Bottom line\n- x")])
        self.assertEqual(out, "## Bottom line\n- x")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["messages"][-1]["role"], "assistant")
        self.assertEqual(calls[0]["tools"][0]["type"], "web_search_20260209")

    def test_refusal_returns_none(self):
        out, _ = self.run_with([msg("refusal")])
        self.assertIsNone(out)

    def test_skipped_without_key(self):
        self.assertIsNone(analyst.write_briefing({"secrets": {}}, {}, [], [], []))


if __name__ == "__main__":
    unittest.main()
