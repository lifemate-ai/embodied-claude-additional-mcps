"""Tests for the send_line_message / check_line_messages tools."""

from pathlib import Path

from line_bot_mcp import server


def test_send_empty_rejected():
    assert server.send_line_message("") == "Error: text is empty"
    assert server.send_line_message("   ") == "Error: text is empty"


def test_send_too_long_rejected():
    result = server.send_line_message("あ" * (server.MAX_LEN + 1))
    assert result.startswith("Error: text too long")


def test_send_without_token_reports_error(monkeypatch):
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LINE_OWNER_USER_ID", raising=False)
    result = server.send_line_message("やあ")
    assert "not set" in result


def test_send_success_calls_push(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    captured = {}

    def fake_push(token, to, text):
        captured.update(token=token, to=to, text=text)

    monkeypatch.setattr(server.line_client, "push", fake_push)
    result = server.send_line_message("やあ")
    assert result == "sent (len=2)"
    assert captured == {"token": "tok", "to": "U1", "text": "やあ"}


def test_send_surfaces_push_failure(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")

    def boom(token, to, text):
        raise RuntimeError("429 too many")

    monkeypatch.setattr(server.line_client, "push", boom)
    result = server.send_line_message("hi")
    assert result == "Error: 429 too many"


def test_check_without_table(monkeypatch):
    monkeypatch.setenv("LINE_INBOX_TABLE", "")
    result = server.check_line_messages()
    assert "not set" in result


def test_fetch_line_image_returns_image_from_local(tmp_path, monkeypatch):
    from mcp.server.fastmcp import Image

    monkeypatch.setattr("line_bot_mcp.poller._media_dir", lambda cfg: tmp_path)
    p = tmp_path / "img1.jpg"
    p.write_bytes(b"\xff\xd8jpeg")
    result = server.fetch_line_image(str(p))
    assert isinstance(result, Image)
    assert result.to_image_content().mimeType == "image/jpeg"


def test_fetch_line_image_rejects_path_outside_cache(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("line_bot_mcp.poller._media_dir", lambda cfg: cache)
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"top secret")
    result = server.fetch_line_image(str(secret))
    assert "outside" in result


def test_fetch_line_image_resolves_message_id(tmp_path, monkeypatch):
    from mcp.server.fastmcp import Image

    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("line_bot_mcp.poller._media_dir", lambda cfg: cache)
    (cache / "abc123.jpg").write_bytes(b"\xff\xd8x")
    result = server.fetch_line_image("abc123")
    assert isinstance(result, Image)


def test_fetch_line_image_missing_message_id(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("line_bot_mcp.poller._media_dir", lambda cfg: cache)
    result = server.fetch_line_image("nonexistent")
    assert "no cached image" in result


def test_send_image_without_media_config_errors(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.delenv("LINE_MEDIA_S3_BUCKET", raising=False)
    result = server.send_line_image("/tmp/whatever.jpg")
    assert "not set" in result


def test_send_image_uploads_and_pushes(monkeypatch, tmp_path):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.setenv("LINE_MEDIA_S3_BUCKET", "b")
    src = tmp_path / "photo.jpg"
    src.write_bytes(b"img")
    monkeypatch.setattr(server.media, "ensure_tools", lambda: None)
    monkeypatch.setattr(server.media, "make_preview", lambda s, d, **k: Path(d))
    urls = iter(["https://orig", "https://prev"])
    monkeypatch.setattr(server.media, "upload_and_sign", lambda *a, **k: next(urls))
    captured = {}
    monkeypatch.setattr(
        server.line_client,
        "push_image",
        lambda token, to, o, p: captured.update(o=o, p=p, to=to),
    )
    result = server.send_line_image(str(src))
    assert result.startswith("sent image")
    assert captured == {"o": "https://orig", "p": "https://prev", "to": "U1"}


def test_send_image_too_large_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.setenv("LINE_MEDIA_S3_BUCKET", "b")
    monkeypatch.setattr(server.media, "ensure_tools", lambda: None)
    src = tmp_path / "big.jpg"
    src.write_bytes(b"0" * (10 * 1024 * 1024 + 1))
    result = server.send_line_image(str(src))
    assert "too large" in result


def test_send_audio_converts_and_pushes(monkeypatch, tmp_path):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.setenv("LINE_MEDIA_S3_BUCKET", "b")
    src = tmp_path / "voice.mp3"
    src.write_bytes(b"audio")
    monkeypatch.setattr(server.media, "ensure_tools", lambda: None)
    monkeypatch.setattr(
        server.media, "to_m4a", lambda s, d: (Path(d).write_bytes(b"m4a"), Path(d))[1]
    )
    monkeypatch.setattr(server.media, "ffprobe_duration_ms", lambda p: 5000)
    monkeypatch.setattr(server.media, "upload_and_sign", lambda *a, **k: "https://audio")
    captured = {}
    monkeypatch.setattr(
        server.line_client,
        "push_audio",
        lambda token, to, url, dur: captured.update(url=url, dur=dur),
    )
    result = server.send_line_audio(str(src))
    assert result.startswith("sent audio")
    assert captured == {"url": "https://audio", "dur": 5000}


def test_send_audio_too_long_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.setenv("LINE_MEDIA_S3_BUCKET", "b")
    src = tmp_path / "long.mp3"
    src.write_bytes(b"audio")
    monkeypatch.setattr(server.media, "ensure_tools", lambda: None)
    monkeypatch.setattr(
        server.media, "to_m4a", lambda s, d: (Path(d).write_bytes(b"x"), Path(d))[1]
    )
    monkeypatch.setattr(server.media, "ffprobe_duration_ms", lambda p: 70000)
    result = server.send_line_audio(str(src))
    assert "too long" in result


def test_send_audio_source_too_large_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.setenv("LINE_MEDIA_S3_BUCKET", "b")
    monkeypatch.setattr(server.media, "ensure_tools", lambda: None)
    src = tmp_path / "huge.wav"
    with open(src, "wb") as f:  # sparse file: large st_size, ~no disk use
        f.seek(server._MAX_AUDIO_SRC_BYTES)
        f.write(b"x")
    result = server.send_line_audio(str(src))
    assert "too large" in result


def test_send_audio_without_media_config_errors(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.delenv("LINE_MEDIA_S3_BUCKET", raising=False)
    result = server.send_line_audio("/tmp/whatever.m4a")
    assert "not set" in result


def test_send_image_png_content_type(monkeypatch, tmp_path):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.setenv("LINE_MEDIA_S3_BUCKET", "b")
    src = tmp_path / "photo.png"
    src.write_bytes(b"\x89PNG")
    monkeypatch.setattr(server.media, "ensure_tools", lambda: None)
    monkeypatch.setattr(server.media, "make_preview", lambda s, d, **k: Path(d))
    calls = []

    def fake_upload(*a, **k):
        calls.append(a)
        return "https://u"

    monkeypatch.setattr(server.media, "upload_and_sign", fake_upload)
    monkeypatch.setattr(server.line_client, "push_image", lambda *a: None)
    server.send_line_image(str(src))
    assert calls[0][2] == "image/png"  # original upload's content_type arg


def test_fetch_line_image_png_format(tmp_path, monkeypatch):
    from mcp.server.fastmcp import Image

    monkeypatch.setattr("line_bot_mcp.poller._media_dir", lambda cfg: tmp_path)
    p = tmp_path / "i.png"
    p.write_bytes(b"\x89PNG")
    result = server.fetch_line_image(str(p))
    assert isinstance(result, Image)
    assert result.to_image_content().mimeType == "image/png"


def _stub_audio_send(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.setenv("LINE_MEDIA_S3_BUCKET", "b")

    def fake_to_m4a(s, d):
        Path(d).write_bytes(b"x")
        return Path(d)

    monkeypatch.setattr(server.media, "ensure_tools", lambda: None)
    monkeypatch.setattr(server.media, "to_m4a", fake_to_m4a)
    monkeypatch.setattr(server.media, "upload_and_sign", lambda *a, **k: "https://a")
    monkeypatch.setattr(server.line_client, "push_audio", lambda *a: None)


def test_send_audio_boundary_60000_ok(monkeypatch, tmp_path):
    _stub_audio_send(monkeypatch)
    monkeypatch.setattr(server.media, "ffprobe_duration_ms", lambda p: 60000)
    src = tmp_path / "v.mp3"
    src.write_bytes(b"a")
    assert server.send_line_audio(str(src)).startswith("sent audio")


def test_send_audio_61000_too_long(monkeypatch, tmp_path):
    _stub_audio_send(monkeypatch)
    monkeypatch.setattr(server.media, "ffprobe_duration_ms", lambda p: 60001)
    src = tmp_path / "v.mp3"
    src.write_bytes(b"a")
    assert "too long" in server.send_line_audio(str(src))


def test_send_audio_duration_zero_errors(monkeypatch, tmp_path):
    _stub_audio_send(monkeypatch)
    monkeypatch.setattr(server.media, "ffprobe_duration_ms", lambda p: 0)
    src = tmp_path / "v.mp3"
    src.write_bytes(b"a")
    assert "could not determine" in server.send_line_audio(str(src))


def test_check_line_messages_success(monkeypatch):
    from line_bot_mcp import poller

    monkeypatch.setenv("LINE_INBOX_TABLE", "t")
    monkeypatch.setattr(
        poller, "peek_unprocessed", lambda cfg, limit: [{"person": "owner", "text": "hi"}]
    )
    assert server.check_line_messages() == "[owner] hi"
