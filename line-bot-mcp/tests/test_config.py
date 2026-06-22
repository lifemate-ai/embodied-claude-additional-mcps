"""Tests for media-related config (S3 bucket, presigned URL TTL)."""

from line_bot_mcp.config import Config


def test_can_send_media_true_with_token_owner_bucket(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.setenv("LINE_MEDIA_S3_BUCKET", "my-bucket")
    cfg = Config.from_env()
    assert cfg.can_send_media is True


def test_can_send_media_false_without_bucket(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.delenv("LINE_MEDIA_S3_BUCKET", raising=False)
    cfg = Config.from_env()
    assert cfg.can_send_media is False


def test_can_send_media_false_without_token(monkeypatch):
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("LINE_OWNER_USER_ID", "U1")
    monkeypatch.setenv("LINE_MEDIA_S3_BUCKET", "my-bucket")
    cfg = Config.from_env()
    assert cfg.can_send_media is False


def test_media_url_ttl_defaults_to_900(monkeypatch):
    monkeypatch.delenv("LINE_MEDIA_URL_TTL", raising=False)
    cfg = Config.from_env()
    assert cfg.media_url_ttl == 900


def test_media_url_ttl_from_env(monkeypatch):
    monkeypatch.setenv("LINE_MEDIA_URL_TTL", "1800")
    cfg = Config.from_env()
    assert cfg.media_url_ttl == 1800
