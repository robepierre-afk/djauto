import unittest

from scout import hardware
from scout.models import ModelCandidate
from scout.report import md_to_html
from scout.textutil import family_key, is_non_commercial, music_category, parse_params_from_name

MACHINE = {"gpu_vram_gb": 24, "system_ram_gb": 64}


def llm(name, params, active=None, moe=None):
    return ModelCandidate(repo_id=f"org/{name}", category="llm", source="huggingface", url="",
                          params_b=params, active_params_b=active, is_moe=bool(active) if moe is None else moe)


class TextUtil(unittest.TestCase):
    def test_params_from_name(self):
        self.assertEqual(parse_params_from_name("Qwen3-30B-A3B-Instruct"), (30.0, 3.0))
        self.assertEqual(parse_params_from_name("gemma-3-27b-it"), (27.0, None))
        self.assertEqual(parse_params_from_name("SmolLM2-360M"), (0.36, None))
        self.assertEqual(parse_params_from_name("Mixtral-8x7B")[0], 47.6)
        self.assertEqual(parse_params_from_name("ACE-Step-v1-3.5B"), (3.5, None))
        self.assertEqual(parse_params_from_name("musicgen-large"), (None, None))

    def test_family_key(self):
        self.assertEqual(family_key("Qwen3-235B-A22B-Instruct-2507"), "qwen3")
        self.assertEqual(family_key("gpt-oss-120b"), "gpt-oss")
        self.assertEqual(family_key("DeepSeek-V3.2"), "deepseek-v3.2")

    def test_music_category(self):
        self.assertEqual(music_category("spotify/basic-pitch audio to midi transcription"), "music_score")
        self.assertEqual(music_category("facebookresearch/demucs source separation"), "music_analysis")
        self.assertEqual(music_category("ACE-Step text-to-music song generation"), "music_generation")

    def test_non_commercial(self):
        self.assertTrue(is_non_commercial("cc-by-nc-4.0"))
        self.assertTrue(is_non_commercial("stabilityai-research"))
        self.assertFalse(is_non_commercial("apache-2.0"))
        self.assertFalse(is_non_commercial("mit"))


class Hardware(unittest.TestCase):
    def assess(self, c, machine=MACHINE):
        hardware.assess(c, machine)
        return c.fit

    def test_small_dense_fp16(self):
        c = llm("x-8B", 8)
        self.assertEqual(self.assess(c), "gpu")
        self.assertIn("FP16", c.fit_detail)  # ~18 GB fits in 24 GB

    def test_14b_q8(self):
        c = llm("x-14B", 14)
        self.assertEqual(self.assess(c), "gpu")
        self.assertIn("Q8", c.fit_detail)

    def test_32b_needs_q4(self):
        c = llm("x-32B", 32)
        self.assertEqual(self.assess(c), "gpu")
        self.assertIn("Q4", c.fit_detail)

    def test_moe_offload(self):
        c = llm("x-120B-A5B", 117, 5.1)
        self.assertEqual(self.assess(c), "offload")

    def test_moe_from_config_without_active(self):
        self.assertEqual(self.assess(llm("gpt-oss-120b", 120.4, moe=True)), "offload")

    def test_dense_70b_slow(self):
        self.assertEqual(self.assess(llm("x-70B", 70)), "offload_slow")

    def test_too_big(self):
        self.assertEqual(self.assess(llm("x-671B", 671, 37)), "too_big")

    def test_unified_memory(self):
        mac = {"gpu_vram_gb": 0, "system_ram_gb": 128, "unified_memory": True}
        self.assertEqual(self.assess(llm("x-70B", 70), mac), "gpu")

    def test_unknown_size(self):
        c = ModelCandidate(repo_id="a/b", category="music_score", source="github", url="")
        self.assertEqual(self.assess(c), "check")


class Markdown(unittest.TestCase):
    def test_basic(self):
        h = md_to_html("## Head\n\n- **Bold** [link](https://x.y)\n- two\n\nPara <b>")
        self.assertIn("<h3>Head</h3>", h)
        self.assertIn("<li><b>Bold</b> <a href='https://x.y'>link</a></li>", h)
        self.assertIn("<p>Para &lt;b&gt;</p>", h)


if __name__ == "__main__":
    unittest.main()
