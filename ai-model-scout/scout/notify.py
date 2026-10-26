"""Send a short Telegram summary when the report is ready."""

from __future__ import annotations

import logging

from . import http

log = logging.getLogger(__name__)


def telegram(token: str, chat_id: str, lines: list[str], report_path: str) -> None:
    if not token or not chat_id:
        log.info("Telegram not configured; skipping notification")
        return
    text = "AI Model Scout: weekly report ready\n\n" + "\n\n".join(lines) + f"\n\nReport: {report_path}"
    try:
        http.post_json(f"https://api.telegram.org/bot{token}/sendMessage",
                       {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True})
    except http.FetchError as e:
        log.warning("Telegram notification failed: %s", e)
