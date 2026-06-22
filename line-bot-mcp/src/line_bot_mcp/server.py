"""LINE BOT MCP server.

Outbound (AI -> owner): send_line_message / send_line_image / send_line_audio.
Inbound (owner -> AI): fetch_line_image (reads a poller-cached image), plus the
read-only check_line_messages peek. The main inbound path is hook injection
(text + poller-transcribed audio + image-arrival notices), not these tools.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from . import line_client, media
from .config import Config

mcp = FastMCP("line-bot")

MAX_LEN = 5000
_MAX_MEDIA_BYTES = 10 * 1024 * 1024
_MAX_AUDIO_MS = 60_000
_MAX_AUDIO_SRC_BYTES = 50 * 1024 * 1024  # reject oversized source before transcoding


@mcp.tool()
def send_line_message(text: str) -> str:
    """オーナーの LINE に push メッセージを送る（AI能動発信）。

    Args:
        text: 本文（最大5000字、改行可）。
    """
    text = (text or "").strip()
    if not text:
        return "Error: text is empty"
    if len(text) > MAX_LEN:
        return f"Error: text too long ({len(text)} > {MAX_LEN})"
    cfg = Config.from_env()
    if not cfg.can_send:
        return "Error: LINE_CHANNEL_ACCESS_TOKEN or LINE_OWNER_USER_ID not set"
    try:
        line_client.push(cfg.channel_access_token, cfg.owner_user_id, text)
    except Exception as e:  # noqa: BLE001 - surface any failure as a tool error string
        return f"Error: {e}"
    return f"sent (len={len(text)})"


@mcp.tool()
def check_line_messages(limit: int = 10) -> str:
    """DynamoDB の未処理 LINE メッセージを読み取り専用で覗く。

    processed フラグは更新せず、主経路（hook 注入）の消費と競合させない。
    introspection 用の補助ツール。

    Args:
        limit: 取得する最大件数（1-50）。
    """
    cfg = Config.from_env()
    if not cfg.can_poll:
        return "Error: LINE_INBOX_TABLE not set"
    limit = max(1, min(50, limit))
    try:
        from . import poller

        msgs = poller.peek_unprocessed(cfg, limit)
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}"
    if not msgs:
        return "(no unprocessed messages)"
    return "\n".join(f"[{m.get('person', '?')}] {m.get('text', '')}" for m in msgs)


@mcp.tool()
def fetch_line_image(ref: str):
    """owner が送ってきた画像（ポーラーがキャッシュ済み）を取得して表示する。

    Args:
        ref: ポーラーが保存したローカル画像パス（hook が案内する）、または LINE message_id。
            いずれもメディアキャッシュ配下に限定する（キャッシュ外のファイルは読まない）。
    """
    from .poller import _media_dir

    base = _media_dir(Config.from_env()).resolve()
    p = Path(ref)
    if not p.is_absolute() and p.name == ref:
        # bare message_id: resolve within the poller media cache
        matches = sorted(base.glob(f"{ref}.*"))
        if not matches:
            return f"Error: no cached image for '{ref}'"
        p = matches[0]
    try:
        resolved = p.resolve()
    except OSError as e:  # noqa: BLE001
        return f"Error: {e}"
    if not resolved.is_relative_to(base):
        return "Error: path is outside the LINE media cache"
    if not resolved.exists():
        return f"Error: file not found: {ref}"
    fmt = "png" if resolved.suffix.lower() == ".png" else "jpeg"
    return Image(data=resolved.read_bytes(), format=fmt)


@mcp.tool()
def send_line_image(image_path: str) -> str:
    """画像（カメラのキャプチャなど）を owner の LINE に送る。

    Args:
        image_path: 送りたい画像ファイルのパス（JPEG/PNG、最大10MB）。
    """
    cfg = Config.from_env()
    if not cfg.can_send_media:
        return (
            "Error: LINE_CHANNEL_ACCESS_TOKEN / LINE_OWNER_USER_ID / LINE_MEDIA_S3_BUCKET not set"
        )
    src = Path(image_path)
    if not src.exists():
        return f"Error: file not found: {image_path}"
    try:
        media.ensure_tools()
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}"
    size = src.stat().st_size
    if size > _MAX_MEDIA_BYTES:
        return f"Error: image too large ({size} bytes > 10MB)"
    ext = src.suffix.lower().lstrip(".") or "jpg"
    ctype = "image/png" if ext == "png" else "image/jpeg"
    try:
        with tempfile.TemporaryDirectory() as td:
            preview = media.make_preview(src, Path(td) / "preview.jpg")
            original_url = media.upload_and_sign(
                cfg.media_s3_bucket, src, ctype, cfg.aws_region, cfg.media_url_ttl, ext
            )
            preview_url = media.upload_and_sign(
                cfg.media_s3_bucket, preview, "image/jpeg", cfg.aws_region, cfg.media_url_ttl, "jpg"
            )
        line_client.push_image(
            cfg.channel_access_token, cfg.owner_user_id, original_url, preview_url
        )
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}"
    return f"sent image ({size} bytes)"


@mcp.tool()
def send_line_audio(audio_path: str) -> str:
    """音声を owner の LINE に送る（m4a に変換、最大1分）。

    Args:
        audio_path: 送りたい音声ファイルのパス。
    """
    cfg = Config.from_env()
    if not cfg.can_send_media:
        return (
            "Error: LINE_CHANNEL_ACCESS_TOKEN / LINE_OWNER_USER_ID / LINE_MEDIA_S3_BUCKET not set"
        )
    src = Path(audio_path)
    if not src.exists():
        return f"Error: file not found: {audio_path}"
    try:
        media.ensure_tools()
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}"
    if src.stat().st_size > _MAX_AUDIO_SRC_BYTES:
        return f"Error: source audio too large ({src.stat().st_size} bytes)"
    try:
        with tempfile.TemporaryDirectory() as td:
            m4a = media.to_m4a(src, Path(td) / "audio.m4a")
            duration = media.ffprobe_duration_ms(m4a)
            if duration <= 0:
                return "Error: could not determine audio duration"
            if duration > _MAX_AUDIO_MS:
                return f"Error: audio too long ({duration} ms > 60s LINE limit)"
            if Path(m4a).stat().st_size > _MAX_MEDIA_BYTES:
                return "Error: audio too large (> 10MB)"
            url = media.upload_and_sign(
                cfg.media_s3_bucket, m4a, "audio/m4a", cfg.aws_region, cfg.media_url_ttl, "m4a"
            )
            line_client.push_audio(cfg.channel_access_token, cfg.owner_user_id, url, duration)
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}"
    return f"sent audio ({duration} ms)"


def main() -> None:
    """Entry point for the ``line-bot-mcp`` script."""
    mcp.run()
