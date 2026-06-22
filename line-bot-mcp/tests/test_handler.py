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


def _raising_table(code):
    """A stub table whose put_item raises a ClientError with the given code."""
    from botocore.exceptions import ClientError

    def put_item(self, **k):
        raise ClientError({"Error": {"Code": code}}, "PutItem")

    return type("T", (), {"put_item": put_item})()


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
    assert item["type"] == "text"
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


def test_image_message_stored(monkeypatch):
    h = _load_handler(monkeypatch)
    puts = []
    monkeypatch.setattr(h, "_table", lambda: _fake_table(puts))
    body = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "image", "id": "img1"},
                    "source": {"userId": "Uowner"},
                    "timestamp": 100,
                }
            ]
        }
    ).encode()
    res = h.handler(_event(body), None)
    assert res["statusCode"] == 200
    assert len(puts) == 1
    item = puts[0]["Item"]
    assert item["message_id"] == "img1"
    assert item["type"] == "image"
    assert item["person"] == "owner"
    assert item["text"] == ""
    assert item["processed"] == 0


def test_audio_message_stored_with_duration(monkeypatch):
    h = _load_handler(monkeypatch)
    puts = []
    monkeypatch.setattr(h, "_table", lambda: _fake_table(puts))
    body = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "audio", "id": "aud1", "duration": 5000},
                    "source": {"userId": "Uowner"},
                    "timestamp": 100,
                }
            ]
        }
    ).encode()
    h.handler(_event(body), None)
    item = puts[0]["Item"]
    assert item["type"] == "audio"
    assert item["duration"] == 5000
    assert item["processed"] == 0


def test_video_message_skipped(monkeypatch):
    h = _load_handler(monkeypatch)
    puts = []
    monkeypatch.setattr(h, "_table", lambda: _fake_table(puts))
    body = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "video", "id": "v1"},
                    "source": {"userId": "Uowner"},
                }
            ]
        }
    ).encode()
    h.handler(_event(body), None)
    assert puts == []


def _text_event_body(mid="m1"):
    return json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "text", "id": mid, "text": "hi"},
                    "source": {"userId": "Uowner"},
                    "timestamp": 1,
                }
            ]
        }
    ).encode()


def test_duplicate_webhook_swallowed(monkeypatch):
    h = _load_handler(monkeypatch)
    monkeypatch.setattr(h, "_table", lambda: _raising_table("ConditionalCheckFailedException"))
    # redelivery of an already-stored message must not error
    assert h.handler(_event(_text_event_body()), None)["statusCode"] == 200


def test_other_clienterror_propagates(monkeypatch):
    import pytest
    from botocore.exceptions import ClientError

    h = _load_handler(monkeypatch)
    monkeypatch.setattr(h, "_table", lambda: _raising_table("ValidationException"))
    with pytest.raises(ClientError):
        h.handler(_event(_text_event_body()), None)


def test_text_missing_id_skipped(monkeypatch):
    h = _load_handler(monkeypatch)
    puts = []
    monkeypatch.setattr(h, "_table", lambda: _fake_table(puts))
    body = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "text", "text": "no id"},
                    "source": {"userId": "Uowner"},
                }
            ]
        }
    ).encode()
    h.handler(_event(body), None)
    assert puts == []


def test_invalid_json_body_returns_200(monkeypatch):
    h = _load_handler(monkeypatch)
    body = b"not json at all"
    # signature is valid; the body just isn't JSON -> swallow with 200
    assert h.handler(_event(body), None)["statusCode"] == 200
