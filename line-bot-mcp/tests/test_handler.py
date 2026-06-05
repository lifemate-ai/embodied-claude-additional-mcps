"""Tests for the Lambda webhook handler (signature, routing, dedup)."""

import base64
import hashlib
import hmac
import importlib
import json
import sys
from pathlib import Path

_LAMBDA_DIR = str(Path(__file__).parent.parent / "lambda")
_SECRET = "testsecret"


def _load_handler(monkeypatch, owner_id="Uowner"):
    monkeypatch.setenv("LINE_CHANNEL_SECRET", _SECRET)
    monkeypatch.setenv("INBOX_TABLE", "dummy")
    monkeypatch.setenv("LINE_OWNER_USER_ID", owner_id)
    if _LAMBDA_DIR not in sys.path:
        sys.path.insert(0, _LAMBDA_DIR)
    import handler as h

    importlib.reload(h)
    return h


def _sign(body: bytes) -> str:
    return base64.b64encode(hmac.new(_SECRET.encode(), body, hashlib.sha256).digest()).decode()


def _event(body: bytes, sig: str | None = None) -> dict:
    return {
        "headers": {"x-line-signature": sig if sig is not None else _sign(body)},
        "body": body.decode(),
        "isBase64Encoded": False,
    }


def _fake_table(puts):
    """A stub DynamoDB table that records put_item calls into ``puts``."""
    return type("T", (), {"put_item": lambda self, **k: puts.append(k)})()


def test_verify_signature(monkeypatch):
    h = _load_handler(monkeypatch)
    body = b'{"events":[]}'
    assert h.verify_signature(body, _sign(body)) is True
    assert h.verify_signature(body, "wrong") is False


def test_bad_signature_returns_403(monkeypatch):
    h = _load_handler(monkeypatch)
    body = b'{"events":[]}'
    assert h.handler(_event(body, "nope"), None)["statusCode"] == 403


def test_empty_events_returns_200_no_put(monkeypatch):
    h = _load_handler(monkeypatch)
    puts = []
    monkeypatch.setattr(h, "_table", lambda: _fake_table(puts))
    body = json.dumps({"events": []}).encode()
    assert h.handler(_event(body), None)["statusCode"] == 200
    assert puts == []


def test_text_message_stored_with_person(monkeypatch):
    h = _load_handler(monkeypatch)
    puts = []
    monkeypatch.setattr(h, "_table", lambda: _fake_table(puts))
    body = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "text", "id": "m1", "text": "おはよう"},
                    "source": {"userId": "Uowner"},
                    "timestamp": 123,
                }
            ]
        }
    ).encode()
    res = h.handler(_event(body), None)
    assert res["statusCode"] == 200
    assert len(puts) == 1
    item = puts[0]["Item"]
    assert item["message_id"] == "m1"
    assert item["person"] == "owner"
    assert item["text"] == "おはよう"
    assert item["processed"] == 0


def test_non_text_message_skipped(monkeypatch):
    h = _load_handler(monkeypatch)
    puts = []
    monkeypatch.setattr(h, "_table", lambda: _fake_table(puts))
    body = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "sticker", "id": "s1"},
                    "source": {"userId": "Uowner"},
                }
            ]
        }
    ).encode()
    h.handler(_event(body), None)
    assert puts == []


def test_unknown_user_marked_unknown(monkeypatch):
    h = _load_handler(monkeypatch)
    puts = []
    monkeypatch.setattr(h, "_table", lambda: _fake_table(puts))
    body = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "text", "id": "m2", "text": "hi"},
                    "source": {"userId": "Ustranger"},
                    "timestamp": 1,
                }
            ]
        }
    ).encode()
    h.handler(_event(body), None)
    assert puts[0]["Item"]["person"] == "unknown"
