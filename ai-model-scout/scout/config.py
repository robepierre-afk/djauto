"""Load config.toml (falls back to config.example.toml) and environment secrets."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent


def load_config(path: str | None = None) -> dict:
    candidates = [Path(path)] if path else [APP_DIR / "config.toml", APP_DIR / "config.example.toml"]
    for p in candidates:
        if p.exists():
            with open(p, "rb") as f:
                cfg = tomllib.load(f)
            cfg["_path"] = str(p)
            break
    else:
        raise FileNotFoundError(f"No config found in {candidates}")

    # Secrets come from the environment (or a .env file next to the app), never from git.
    _load_dotenv(APP_DIR / ".env")
    cfg["secrets"] = {
        k: os.environ.get(k, "")
        for k in ("YOUTUBE_API_KEY", "GITHUB_TOKEN", "HF_TOKEN", "ANTHROPIC_API_KEY",
                  "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    }
    return cfg


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in ('"', "'"):
            value = value[1:].split(value[0], 1)[0]
        else:
            # "KEY=   # note" means no value; "KEY=abc  # note" means abc.
            value = "" if value.startswith("#") else re.split(r"\s+#", value, maxsplit=1)[0]
        if value:
            os.environ.setdefault(key.strip(), value)
