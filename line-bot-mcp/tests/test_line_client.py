"""Tests for the LINE push client (retry behaviour, httpx mocked)."""

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
