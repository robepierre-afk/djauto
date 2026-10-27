"""Tiny stdlib HTTP helper with retries, so the app has no hard dependencies."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "ai-model-scout/1.0 (+weekly open-model digest)"


class FetchError(RuntimeError):
    pass


def get(url: str, params: dict | list | None = None, headers: dict | None = None,
        timeout: int = 30, retries: int = 3) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    hdrs.update(headers or {})
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            # 4xx other than rate limiting won't get better on retry.
            if e.code < 500 and e.code != 429:
                break
            if e.code == 429:
                retry_after = e.headers.get("Retry-After", "") if e.headers else ""
                pause(min(int(retry_after), 60) if retry_after.isdigit() else 10 * (attempt + 1))
                continue
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
        time.sleep(2 ** attempt)
    raise FetchError(f"GET {url} failed: {last_err}")


def pause(seconds: float) -> None:
    time.sleep(seconds)


def get_json(url: str, params: dict | list | None = None, headers: dict | None = None, **kw):
    return json.loads(get(url, params, {"Accept": "application/json", **(headers or {})}, **kw))


def post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 30) -> dict:
    hdrs = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise FetchError(f"POST {url} failed: {e.code} {e.read()[:300]!r}") from e
