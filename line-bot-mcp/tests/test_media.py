"""Tests for media helpers (ffmpeg/ffprobe and S3 isolated via seams)."""

import types
from pathlib import Path

import pytest

from line_bot_mcp import media


def test_ensure_tools_raises_when_missing(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda _t: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        media.ensure_tools()


def test_ensure_tools_ok_when_present(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda t: f"/usr/bin/{t}")
    media.ensure_tools()  # no raise


def test_ffprobe_duration_ms(monkeypatch):
    monkeypatch.setattr(media, "_run", lambda cmd: types.SimpleNamespace(stdout="5.3\n"))
    assert media.ffprobe_duration_ms("/tmp/a.m4a") == 5300


def test_ffprobe_duration_ms_handles_na(monkeypatch):
    monkeypatch.setattr(media, "_run", lambda cmd: types.SimpleNamespace(stdout="N/A\n"))
    assert media.ffprobe_duration_ms("/tmp/a.m4a") == 0


def test_ffprobe_duration_ms_handles_empty(monkeypatch):
    monkeypatch.setattr(media, "_run", lambda cmd: types.SimpleNamespace(stdout="\n"))
    assert media.ffprobe_duration_ms("/tmp/a.m4a") == 0


def test_to_m4a_invokes_ffmpeg(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(media, "_run", lambda cmd: captured.setdefault("cmd", cmd))
    src = tmp_path / "in.wav"
    src.write_bytes(b"x")
    media.to_m4a(src, tmp_path / "out.m4a")
    assert "ffmpeg" in captured["cmd"]
    assert "aac" in captured["cmd"]


def test_to_m4a_skips_when_already_m4a(monkeypatch, tmp_path):
    def no_run(cmd):
        raise AssertionError("should not transcode an m4a")

    monkeypatch.setattr(media, "_run", no_run)
    src = tmp_path / "in.m4a"
    src.write_bytes(b"x")
    out = media.to_m4a(src, tmp_path / "out.m4a")
    assert Path(out).read_bytes() == b"x"


def test_make_preview_invokes_ffmpeg_with_scale(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(media, "_run", lambda cmd: captured.setdefault("cmd", cmd))
    media.make_preview(tmp_path / "in.jpg", tmp_path / "p.jpg")
    cmd = captured["cmd"]
    assert "ffmpeg" in cmd
    assert any("scale" in str(a) for a in cmd)


def test_s3_upload_sets_no_acl(monkeypatch):
    calls = {}

    class FakeClient:
        def upload_file(self, path, bucket, key, ExtraArgs=None):
            calls["args"] = (path, bucket, key, ExtraArgs)

    monkeypatch.setattr(media, "_s3_client", lambda region: FakeClient())
    media.s3_upload("b", "media/x.jpg", "/tmp/x.jpg", "image/jpeg", "ap-northeast-1")
    _path, bucket, key, extra = calls["args"]
    assert bucket == "b"
    assert key == "media/x.jpg"
    assert "ACL" not in extra
    assert extra["ContentType"] == "image/jpeg"


def test_s3_presigned_get(monkeypatch):
    calls = {}

    class FakeClient:
        def generate_presigned_url(self, op, Params=None, ExpiresIn=None):
            calls["args"] = (op, Params, ExpiresIn)
            return "https://signed"

    monkeypatch.setattr(media, "_s3_client", lambda region: FakeClient())
    url = media.s3_presigned_get("b", "media/x.jpg", "ap-northeast-1", expires=900)
    assert url == "https://signed"
    op, params, expires = calls["args"]
    assert op == "get_object"
    assert params == {"Bucket": "b", "Key": "media/x.jpg"}
    assert expires == 900


def test_upload_and_sign_uses_random_media_key(monkeypatch):
    up, sign = {}, {}
    monkeypatch.setattr(
        media,
        "s3_upload",
        lambda b, k, p, c, r: up.update(bucket=b, key=k, path=p, ctype=c, region=r),
    )

    def fake_sign(b, k, r, expires):
        sign.update(bucket=b, key=k, region=r, expires=expires)
        return f"https://signed/{k}"

    monkeypatch.setattr(media, "s3_presigned_get", fake_sign)
    url = media.upload_and_sign("b", "/tmp/x.jpg", "image/jpeg", "ap-northeast-1", 900, "jpg")
    # all args forwarded correctly to s3_upload
    assert up["bucket"] == "b"
    assert up["path"] == "/tmp/x.jpg"
    assert up["ctype"] == "image/jpeg"
    assert up["region"] == "ap-northeast-1"
    assert up["key"].startswith("media/")
    assert up["key"].endswith(".jpg")
    # the uploaded key is the same one that gets signed, with the TTL forwarded
    assert sign["key"] == up["key"]
    assert sign["expires"] == 900
    assert url.endswith(up["key"])
