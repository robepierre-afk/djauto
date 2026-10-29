"""Plain data records shared by collectors, scoring and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelCandidate:
    repo_id: str                      # e.g. "Qwen/Qwen3-32B" (Hugging Face) or "owner/repo" (GitHub)
    category: str                     # "llm", "music_generation", "music_analysis", "music_score"
    source: str                       # "huggingface" | "github"
    url: str
    license: str = "unknown"
    gated: bool = False               # needs a click-through on Hugging Face before download
    params_b: float | None = None     # total parameters, billions
    active_params_b: float | None = None  # MoE active parameters, billions
    is_moe: bool = False              # mixture-of-experts: runs well with part of it in system RAM
    likes: int = 0
    downloads: int = 0
    trending: float = 0.0
    stars: int = 0
    created: str = ""                 # ISO date
    updated: str = ""                 # ISO date
    has_gguf: bool = False            # quantised GGUF build exists (llama.cpp / Ollama / LM Studio)
    pipeline_tag: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)  # titles of videos/posts that mention it
    mention_urls: list[str] = field(default_factory=list)
    summary: str = ""                 # plain-language "what it is", from the model card / repo
    benchmarks: list[dict] = field(default_factory=list)  # self-reported results from the model card
    good_for: list[str] = field(default_factory=list)     # e.g. ["Coding", "Reasoning"]
    watchlisted: bool = False
    # Filled in later
    score: float = 0.0
    fit: str = ""
    fit_detail: str = ""
    is_new: bool = False
    license_note: str = ""

    @property
    def name(self) -> str:
        return self.repo_id.split("/")[-1]


@dataclass
class NewsItem:
    title: str
    url: str
    source: str        # "youtube", "reddit", "arxiv", "hn"
    channel: str = ""  # channel / subreddit / author
    published: str = ""
    summary: str = ""
    topic: str = ""    # "llm" or "music"
