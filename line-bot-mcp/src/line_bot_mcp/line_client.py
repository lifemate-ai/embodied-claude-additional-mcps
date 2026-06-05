"""LINE Messaging API push client (outbound: AI -> owner).

Thin synchronous wrapper around the push endpoint with a short retry on
transient (429/5xx) failures. 4xx errors are raised immediately.
"""

from __future__ import annotations

import time

import httpx

PUSH_URL = "https://api.line.me/v2/bot/message/push"
_RETRY_BACKOFFS = (0.5, 1.5)
_RETRYABLE = {429, 500, 502, 503}


def push(token: str, to: str, text: str) -> None:
    """Send a single text push message.

    Raises RuntimeError on non-retryable status or after exhausting retries.
    """
    payload = {"to": to, "messages": [{"type": "text", "text": text}]}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    last_err = ""
    with httpx.Client(timeout=10.0) as client:
        for backoff in (0.0, *_RETRY_BACKOFFS):
            if backoff:
                time.sleep(backoff)
            resp = client.post(PUSH_URL, headers=headers, json=payload)
            if resp.status_code == 200:
                return
            last_err = f"{resp.status_code} {resp.text}"
            if resp.status_code not in _RETRYABLE:
                raise RuntimeError(last_err)
    raise RuntimeError(f"LINE push failed after retries: {last_err}")
