"""LINE Messaging API client (outbound push + inbound content fetch).

Thin synchronous wrappers with a short retry on transient (429/5xx) failures;
4xx errors are raised immediately.
- push / push_image / push_audio: AI -> owner (Messaging API push).
- fetch_content: download a received message's binary (owner -> AI).
"""

from __future__ import annotations

import time

import httpx

PUSH_URL = "https://api.line.me/v2/bot/message/push"
CONTENT_URL = "https://api-data.line.me/v2/bot/message/{}/content"
_RETRY_BACKOFFS = (0.5, 1.5)
_RETRYABLE = {429, 500, 502, 503}


def _push_messages(token: str, to: str, messages: list[dict]) -> None:
    """POST a push payload with retry on 429/5xx; raise on 4xx or exhaustion."""
    payload = {"to": to, "messages": messages}
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


def push(token: str, to: str, text: str) -> None:
    """Send a single text push message."""
    _push_messages(token, to, [{"type": "text", "text": text}])


def push_image(token: str, to: str, original_url: str, preview_url: str) -> None:
    """Send an image message (both URLs must be public HTTPS, JPEG/PNG)."""
    _push_messages(
        token,
        to,
        [{"type": "image", "originalContentUrl": original_url, "previewImageUrl": preview_url}],
    )


def push_audio(token: str, to: str, original_url: str, duration_ms: int) -> None:
    """Send an audio message (m4a HTTPS URL + duration in milliseconds)."""
    _push_messages(
        token,
        to,
        [{"type": "audio", "originalContentUrl": original_url, "duration": int(duration_ms)}],
    )


def fetch_content(token: str, message_id: str) -> tuple[bytes, str]:
    """Download a received message's binary content (owner -> AI).

    Returns ``(data, content_type)``. Retries 429/5xx, raises RuntimeError on
    4xx or after exhausting retries. Uses a longer read timeout than push since
    media bodies can be up to 10MB.
    """
    url = CONTENT_URL.format(message_id)
    headers = {"Authorization": f"Bearer {token}"}
    last_err = ""
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
    with httpx.Client(timeout=timeout) as client:
        for backoff in (0.0, *_RETRY_BACKOFFS):
            if backoff:
                time.sleep(backoff)
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.content, resp.headers.get("content-type", "")
            last_err = f"{resp.status_code} {resp.text}"
            if resp.status_code not in _RETRYABLE:
                raise RuntimeError(last_err)
    raise RuntimeError(f"LINE content fetch failed after retries: {last_err}")
