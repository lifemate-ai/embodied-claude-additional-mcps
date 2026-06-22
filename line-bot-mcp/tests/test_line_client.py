"""Tests for the LINE push client (retry behaviour, httpx mocked)."""

import json

import httpx
import pytest

from line_bot_mcp import line_client

_REAL_CLIENT = httpx.Client  # capture before any test patches httpx.Client


def _mock_client(handler):
    return _REAL_CLIENT(transport=httpx.MockTransport(handler), timeout=10.0)


def test_push_success(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _mock_client(handler))
    line_client.push("tok", "U1", "hi")
    assert len(calls) == 1


def test_push_4xx_raises_immediately(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, text="bad request")

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _mock_client(handler))
    with pytest.raises(RuntimeError, match="400"):
        line_client.push("tok", "U1", "hi")
    assert len(calls) == 1  # no retry on 4xx


def test_push_retries_5xx_then_succeeds(monkeypatch):
    monkeypatch.setattr(line_client.time, "sleep", lambda _s: None)
    codes = [429, 503, 200]

    def handler(request):
        return httpx.Response(codes.pop(0), json={})

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _mock_client(handler))
    line_client.push("tok", "U1", "hi")
    assert codes == []  # all three attempts consumed


def test_push_exhausts_retries(monkeypatch):
    monkeypatch.setattr(line_client.time, "sleep", lambda _s: None)

    def handler(request):
        return httpx.Response(503, text="unavailable")

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _mock_client(handler))
    with pytest.raises(RuntimeError, match="after retries"):
        line_client.push("tok", "U1", "hi")


def test_push_image_payload(monkeypatch):
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _mock_client(handler))
    line_client.push_image("tok", "U1", "https://x/o.jpg", "https://x/p.jpg")
    msg = captured["body"]["messages"][0]
    assert msg["type"] == "image"
    assert msg["originalContentUrl"] == "https://x/o.jpg"
    assert msg["previewImageUrl"] == "https://x/p.jpg"


def test_push_audio_payload(monkeypatch):
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _mock_client(handler))
    line_client.push_audio("tok", "U1", "https://x/a.m4a", 5000)
    msg = captured["body"]["messages"][0]
    assert msg["type"] == "audio"
    assert msg["originalContentUrl"] == "https://x/a.m4a"
    assert msg["duration"] == 5000
    assert isinstance(msg["duration"], int)


def test_fetch_content_returns_bytes_and_type(monkeypatch):
    def handler(request):
        assert request.url.path.endswith("/m1/content")
        return httpx.Response(
            200, content=b"\xff\xd8jpegdata", headers={"content-type": "image/jpeg"}
        )

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _mock_client(handler))
    data, ctype = line_client.fetch_content("tok", "m1")
    assert data == b"\xff\xd8jpegdata"
    assert ctype == "image/jpeg"


def test_fetch_content_4xx_raises(monkeypatch):
    def handler(request):
        return httpx.Response(404, text="not found")

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _mock_client(handler))
    with pytest.raises(RuntimeError, match="404"):
        line_client.fetch_content("tok", "gone")


def test_fetch_content_retries_5xx_then_succeeds(monkeypatch):
    monkeypatch.setattr(line_client.time, "sleep", lambda _s: None)
    codes = [503, 200]

    def handler(request):
        code = codes.pop(0)
        if code == 200:
            return httpx.Response(200, content=b"ok", headers={"content-type": "audio/m4a"})
        return httpx.Response(code, text="unavailable")

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _mock_client(handler))
    data, ctype = line_client.fetch_content("tok", "m1")
    assert data == b"ok"
    assert codes == []
