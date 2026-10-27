"""Hugging Face Hub: the main place open weights are published."""

from __future__ import annotations

import logging

from .. import http
from ..models import ModelCandidate
from ..textutil import days_ago, is_music, iso_date, music_category, parse_params_from_name

API = "https://huggingface.co/api/models"
EXPAND = ["author", "cardData", "config", "createdAt", "downloads", "gated", "lastModified", "likes",
          "pipeline_tag", "safetensors", "tags", "trendingScore"]
LLM_TAGS = {"text-generation", "image-text-to-text", "any-to-any"}
# model_type / architecture fragments that mean mixture-of-experts.
MOE_MARKERS = ("moe", "gpt_oss", "gptoss", "deepseek_v2", "deepseek_v3", "deepseekv3", "mixtral", "llama4",
               "kimi", "dbrx", "jamba", "minimax", "longcat", "hunyuan_v1_moe", "bailing")
SKIP_MARKERS = ("gguf", "awq", "gptq", "exl2", "mlx", "-fp8", "-int4", "-int8", "bnb-4bit", "-quant")

log = logging.getLogger(__name__)


class HuggingFace:
    def __init__(self, cfg: dict, token: str = ""):
        self.cfg = cfg.get("huggingface", {})
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def _query(self, **params) -> list[dict]:
        q = list(params.items()) + [("expand[]", e) for e in EXPAND]
        try:
            return http.get_json(API, q, self.headers)
        except http.FetchError as e:
            log.warning("Hugging Face query %s failed: %s", params, e)
            return []

    # ---- LLMs -------------------------------------------------------------
    def collect_llms(self) -> list[ModelCandidate]:
        raw: dict[str, dict] = {}
        quantised_bases: set[str] = set()

        rows = self._query(pipeline_tag="text-generation", sort="trendingScore", direction=-1, limit=100)
        rows += self._query(pipeline_tag="image-text-to-text", sort="trendingScore", direction=-1, limit=30)
        for author in self.cfg.get("llm_authors", []):
            rows += self._query(author=author, sort="createdAt", direction=-1, limit=15)

        for r in rows:
            rid = r.get("id", "")
            tags = r.get("tags", [])
            base_q = [t.split(":", 2)[2] for t in tags if t.startswith("base_model:quantized:")]
            if base_q or any(m in rid.lower() for m in SKIP_MARKERS):
                # A quantised re-upload: credit the base model with a GGUF build, don't list it.
                if "gguf" in tags or "gguf" in rid.lower():
                    quantised_bases.update(base_q)
                continue
            if r.get("pipeline_tag") not in LLM_TAGS:
                continue
            raw.setdefault(rid, r)

        out = []
        max_age = self.cfg.get("max_age_days", 365)
        for rid, r in raw.items():
            if days_ago(r.get("createdAt", "")) > max_age:
                continue
            c = self._to_candidate(r, "llm")
            c.has_gguf = c.has_gguf or rid in quantised_bases
            out.append(c)
        return out

    # ---- Music --------------------------------------------------------------
    def collect_music(self, watch_ids: list[str]) -> list[ModelCandidate]:
        rows: dict[str, dict] = {}
        for term in self.cfg.get("music_searches", []):
            for r in self._query(search=term, sort="likes", direction=-1, limit=15):
                rows.setdefault(r["id"], r)
        for tag in self.cfg.get("music_pipeline_tags", []):
            for r in self._query(pipeline_tag=tag, sort="trendingScore", direction=-1, limit=50):
                if is_music(r["id"] + " " + " ".join(r.get("tags", [])), r["id"]):
                    rows.setdefault(r["id"], r)
        for rid in watch_ids:
            if "/" in rid and rid not in rows:
                for r in self._query(search=rid.split("/")[-1], author=rid.split("/")[0], limit=5):
                    rows.setdefault(r["id"], r)

        out = []
        max_age = self.cfg.get("max_age_days", 365)
        for rid, r in rows.items():
            low = rid.lower()
            if any(m in low for m in SKIP_MARKERS):
                continue
            watched = any(low == w.lower() or low.startswith(w.lower()) for w in watch_ids)
            if not watched and days_ago(r.get("lastModified", "")) > max_age:
                continue
            text = " ".join([rid, r.get("pipeline_tag") or "", *r.get("tags", [])])
            if not watched and not is_music(text, rid.split("/")[-1]):
                continue
            c = self._to_candidate(r, music_category(text, rid.split("/")[-1], r.get("pipeline_tag") or ""))
            c.watchlisted = watched
            out.append(c)
        return out

    def check_gguf(self, cands: list[ModelCandidate]) -> None:
        """Ask the Hub whether a GGUF quant exists for each LLM (one cheap call per model)."""
        for c in cands:
            if c.has_gguf or c.source != "huggingface":
                continue
            try:
                hits = http.get_json(API, {"filter": f"base_model:quantized:{c.repo_id}", "limit": 1},
                                     self.headers)
            except http.FetchError:
                continue
            c.has_gguf = bool(hits)

    @staticmethod
    def _to_candidate(r: dict, category: str) -> ModelCandidate:
        rid = r["id"]
        tags = r.get("tags", []) or []
        card = r.get("cardData") or {}
        lic = card.get("license") or next((t.split(":", 1)[1] for t in tags if t.startswith("license:")),
                                          "unknown")
        if isinstance(lic, list):
            lic = ",".join(lic)
        if lic == "other" and card.get("license_name"):
            lic = card["license_name"]
        total, active = parse_params_from_name(rid.split("/")[-1])
        st = r.get("safetensors") or {}
        if st.get("total"):
            total = round(st["total"] / 1e9, 2)
        conf = r.get("config") or {}
        arch = " ".join([str(conf.get("model_type", "")), *map(str, conf.get("architectures") or [])]).lower()
        return ModelCandidate(
            repo_id=rid, category=category, source="huggingface",
            is_moe=bool(active) or any(m in arch for m in MOE_MARKERS),
            url=f"https://huggingface.co/{rid}", license=str(lic),
            gated=bool(r.get("gated")), params_b=total, active_params_b=active,
            likes=int(r.get("likes") or 0), downloads=int(r.get("downloads") or 0),
            trending=float(r.get("trendingScore") or 0), created=iso_date(r.get("createdAt")),
            updated=iso_date(r.get("lastModified")), has_gguf="gguf" in tags,
            pipeline_tag=r.get("pipeline_tag") or "", tags=tags,
        )
