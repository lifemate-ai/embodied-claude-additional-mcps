"""Tests for the poller: item normalisation + media fetch/cache/transcribe + drain."""

import json
import time

from line_bot_mcp import poller
from line_bot_mcp.config import Config


def _cfg():
    return Config(
        channel_access_token="tok",
        owner_user_id="U1",
        aws_region="ap-northeast-1",
        inbox_table="t",
        inbox_index="i",
        inbox_jsonl="/tmp/x.jsonl",
        media_s3_bucket="",
        media_url_ttl=900,
    )


def _cfg_with_jsonl(tmp_path):
    return Config(
        channel_access_token="tok",
        owner_user_id="U1",
        aws_region="ap-northeast-1",
        inbox_table="t",
        inbox_index="i",
        inbox_jsonl=str(tmp_path / "inbox.jsonl"),
        media_s3_bucket="",
        media_url_ttl=900,
    )


def test_item_to_dict_defaults_type_text():
    out = poller._item_to_dict({"message_id": "m1", "text": "hi"})
    assert out["type"] == "text"
    assert out["duration"] == 0
    assert out["text"] == "hi"


def test_item_to_dict_preserves_type_and_duration():
    out = poller._item_to_dict({"message_id": "a1", "type": "audio", "duration": 5000})
    assert out["type"] == "audio"
    assert out["duration"] == 5000


def test_fetch_and_cache_text_passthrough(monkeypatch):
    def boom(*a):
        raise AssertionError("text must not fetch content")

    monkeypatch.setattr(poller.line_client, "fetch_content", boom)
    d = {
        "message_id": "m1",
        "person": "owner",
        "type": "text",
        "text": "hi",
        "duration": 0,
        "line_ts": 0,
        "received_at": 0,
    }
    assert poller.fetch_and_cache(_cfg(), d) == d


def test_fetch_and_cache_unknown_person_not_fetched(monkeypatch):
    def boom(*a):
        raise AssertionError("non-owner media must not be fetched")

    monkeypatch.setattr(poller.line_client, "fetch_content", boom)
    d = {
        "message_id": "img1",
        "person": "unknown",
        "type": "image",
        "text": "",
        "duration": 0,
        "line_ts": 0,
        "received_at": 0,
    }
    assert poller.fetch_and_cache(_cfg(), d) == d


def test_fetch_and_cache_image_saves_file(monkeypatch, tmp_path):
    monkeypatch.setattr(poller, "_media_dir", lambda cfg: tmp_path)
    monkeypatch.setattr(
        poller.line_client, "fetch_content", lambda token, mid: (b"\xff\xd8img", "image/jpeg")
    )
    d = {
        "message_id": "img1",
        "person": "owner",
        "type": "image",
        "text": "",
        "duration": 0,
        "line_ts": 0,
        "received_at": 0,
    }
    out = poller.fetch_and_cache(_cfg(), d)
    assert out["media_path"].endswith("img1.jpg")
    assert (tmp_path / "img1.jpg").read_bytes() == b"\xff\xd8img"


def test_transcribe_returns_none_without_faster_whisper(monkeypatch, tmp_path):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "faster_whisper":
            raise ImportError("not installed")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(poller, "_WHISPER_MODEL", None)
    audio = tmp_path / "a.m4a"
    audio.write_bytes(b"x")
    assert poller._transcribe(audio) is None


def test_fetch_and_cache_audio_transcribes(monkeypatch, tmp_path):
    monkeypatch.setattr(poller, "_media_dir", lambda cfg: tmp_path)
    monkeypatch.setattr(
        poller.line_client, "fetch_content", lambda token, mid: (b"m4adata", "audio/m4a")
    )
    monkeypatch.setattr(poller, "_transcribe", lambda path: "こんにちは")
    d = {
        "message_id": "aud1",
        "person": "owner",
        "type": "audio",
        "text": "",
        "duration": 5000,
        "line_ts": 0,
        "received_at": 0,
    }
    out = poller.fetch_and_cache(_cfg(), d)
    assert out["text"] == "こんにちは"
    assert out["media_path"].endswith("aud1.m4a")


def test_fetch_and_cache_audio_no_whisper(monkeypatch, tmp_path):
    monkeypatch.setattr(poller, "_media_dir", lambda cfg: tmp_path)
    monkeypatch.setattr(
        poller.line_client, "fetch_content", lambda token, mid: (b"m4adata", "audio/m4a")
    )
    monkeypatch.setattr(poller, "_transcribe", lambda path: None)
    d = {
        "message_id": "aud2",
        "person": "owner",
        "type": "audio",
        "text": "",
        "duration": 3000,
        "line_ts": 0,
        "received_at": 0,
    }
    out = poller.fetch_and_cache(_cfg(), d)
    assert out["media_path"].endswith("aud2.m4a")
    assert "faster-whisper" in out["text"]


def test_fetch_and_cache_handles_fetch_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(poller, "_media_dir", lambda cfg: tmp_path)

    def boom(token, mid):
        raise RuntimeError("404 expired")

    monkeypatch.setattr(poller.line_client, "fetch_content", boom)
    d = {
        "message_id": "img9",
        "person": "owner",
        "type": "image",
        "text": "",
        "duration": 0,
        "line_ts": 0,
        "received_at": 0,
    }
    out = poller.fetch_and_cache(_cfg(), d)
    assert "media_path" not in out
    assert "失敗" in out["text"]
    assert out["_fetch_failed"] is True


def _query_stub(items):
    return lambda cfg, limit: items


def test_drain_empty_writes_nothing(monkeypatch, tmp_path):
    cfg = _cfg_with_jsonl(tmp_path)
    monkeypatch.setattr(poller, "_query_unprocessed", _query_stub([]))
    assert poller.drain(cfg) == 0
    assert not (tmp_path / "inbox.jsonl").exists()


def test_drain_writes_and_marks_success(monkeypatch, tmp_path):
    cfg = _cfg_with_jsonl(tmp_path)
    items = [
        {"message_id": "m1", "person": "owner", "type": "text", "text": "やあ", "received_at": 1}
    ]
    monkeypatch.setattr(poller, "_query_unprocessed", _query_stub(items))
    marked = []
    monkeypatch.setattr(poller, "_mark_processed", lambda c, ids: marked.extend(ids))
    n = poller.drain(cfg)
    assert n == 1
    lines = (tmp_path / "inbox.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["text"] == "やあ"
    assert "やあ" in lines[0]  # ensure_ascii=False keeps Japanese unescaped
    assert "_fetch_failed" not in rec
    assert marked == ["m1"]


def test_drain_retries_transient_failure(monkeypatch, tmp_path):
    cfg = _cfg_with_jsonl(tmp_path)
    now = int(time.time())
    items = [{"message_id": "img1", "person": "owner", "type": "image", "received_at": now}]
    monkeypatch.setattr(poller, "_query_unprocessed", _query_stub(items))
    monkeypatch.setattr(poller, "_media_dir", lambda c: tmp_path)

    def _boom(token, mid):
        raise RuntimeError("transient network blip")

    monkeypatch.setattr(poller.line_client, "fetch_content", _boom)
    marked = []
    monkeypatch.setattr(poller, "_mark_processed", lambda c, ids: marked.extend(ids))
    n = poller.drain(cfg)
    assert n == 0
    assert marked == []  # not marked -> retried next poll
    assert not (tmp_path / "inbox.jsonl").exists()


def test_drain_gives_up_old_failure(monkeypatch, tmp_path):
    cfg = _cfg_with_jsonl(tmp_path)
    items = [{"message_id": "img1", "person": "owner", "type": "image", "received_at": 0}]
    monkeypatch.setattr(poller, "_query_unprocessed", _query_stub(items))
    monkeypatch.setattr(poller, "_media_dir", lambda c: tmp_path)

    def _boom(token, mid):
        raise RuntimeError("content expired")

    monkeypatch.setattr(poller.line_client, "fetch_content", _boom)
    marked = []
    monkeypatch.setattr(poller, "_mark_processed", lambda c, ids: marked.extend(ids))
    n = poller.drain(cfg)
    assert n == 1
    assert marked == ["img1"]  # old failure -> give up and mark
    rec = json.loads((tmp_path / "inbox.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "失敗" in rec["text"]
    assert "_fetch_failed" not in rec
