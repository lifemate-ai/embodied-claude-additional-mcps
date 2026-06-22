"""DynamoDB inbox poller (inbound: owner -> AI).

Run as the ``line-inbox-poll`` script from cron every ~2 minutes. Queries the
``unprocessed-index`` GSI for messages the Lambda stored, appends them to a
local JSONL file (``~/.claude/line_inbox.jsonl``) for the hook to drain, then
marks them processed. boto3 lives in this package's venv (the system python3
has no boto3), so the hook never touches AWS.
"""

from __future__ import annotations

import fcntl
import json
import time
from pathlib import Path
from typing import Any

from . import line_client
from .config import Config

_MAX_BATCH = 50
_FETCH_GIVEUP_SEC = 3600  # retry transient media-fetch failures up to 1h, then give up
_WHISPER_MODEL = None


def _table(cfg: Config):
    """Return the boto3 DynamoDB Table resource."""
    import boto3

    return boto3.resource("dynamodb", region_name=cfg.aws_region).Table(cfg.inbox_table)


def _query_unprocessed(cfg: Config, limit: int) -> list[dict[str, Any]]:
    """Query the GSI for unprocessed rows, oldest first."""
    table = _table(cfg)
    resp = table.query(
        IndexName=cfg.inbox_index,
        KeyConditionExpression="#p = :p",
        ExpressionAttributeNames={"#p": "processed"},
        ExpressionAttributeValues={":p": 0},
        ScanIndexForward=True,
        Limit=limit,
    )
    return resp.get("Items", [])


def _item_to_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Normalise a DynamoDB item (Decimal etc.) into a plain JSON-safe dict.

    Legacy rows have no ``type`` — they default to "text" for backward compat.
    """
    return {
        "message_id": str(item.get("message_id", "")),
        "person": str(item.get("person", "owner")),
        "type": str(item.get("type", "text")),
        "text": str(item.get("text", "")),
        "duration": int(item.get("duration", 0) or 0),
        "line_ts": int(item.get("line_ts", 0) or 0),
        "received_at": int(item.get("received_at", 0) or 0),
    }


def _media_dir(cfg: Config) -> Path:
    """Directory where received media bodies are cached (sibling of the inbox)."""
    return Path(cfg.inbox_jsonl).parent / "line_media"


def _transcribe(audio_path: Path) -> str | None:
    """Transcribe an m4a with faster-whisper if installed; None if unavailable.

    The model is loaded lazily and cached for the process lifetime, so it is
    only loaded when an audio message actually arrives.
    """
    global _WHISPER_MODEL
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    if _WHISPER_MODEL is None:
        _WHISPER_MODEL = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _info = _WHISPER_MODEL.transcribe(
        str(audio_path),
        language="ja",
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
    )
    return " ".join(seg.text for seg in segments).strip()


def fetch_and_cache(cfg: Config, d: dict[str, Any]) -> dict[str, Any]:
    """Download + cache an owner image/audio body (audio is also transcribed).

    Returns a new dict: image adds ``media_path``; audio adds ``media_path`` and
    sets ``text`` to the transcript. Non-media or non-owner items pass through
    unchanged (owner-only keeps unknown senders from costing fetch/transcribe).
    A fetch failure (e.g. LINE content expired) is recorded in ``text`` without
    a ``media_path``.
    """
    msg_type = d.get("type", "text")
    if msg_type not in ("image", "audio") or d.get("person") != "owner":
        return d
    message_id = d["message_id"]
    try:
        data, _ctype = line_client.fetch_content(cfg.channel_access_token, message_id)
    except Exception as e:  # noqa: BLE001 - transient/expired; flag so drain can retry
        return {**d, "_fetch_failed": True, "text": f"（{msg_type}の取得に失敗しました: {e}）"}
    media_dir = _media_dir(cfg)
    media_dir.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if msg_type == "image" else "m4a"
    path = media_dir / f"{message_id}.{ext}"
    path.write_bytes(data)
    out = {**d, "media_path": str(path)}
    if msg_type == "audio":
        transcript = _transcribe(path)
        out["text"] = transcript or "（音声: 文字起こし不可。faster-whisper 未導入の可能性）"
    return out


def peek_unprocessed(cfg: Config, limit: int = 10) -> list[dict[str, Any]]:
    """Read-only view of unprocessed messages (does not mark them processed)."""
    return [_item_to_dict(it) for it in _query_unprocessed(cfg, limit)]


def _mark_processed(cfg: Config, message_ids: list[str]) -> None:
    table = _table(cfg)
    for mid in message_ids:
        table.update_item(
            Key={"message_id": mid},
            UpdateExpression="SET #p = :one",
            ExpressionAttributeNames={"#p": "processed"},
            ExpressionAttributeValues={":one": 1},
        )


def drain(cfg: Config) -> int:
    """Drain unprocessed messages to the local JSONL and mark them processed.

    Returns the number of messages drained. at-least-once: if the process dies
    after appending but before marking, the hook's seen-set dedups on re-drain.
    """
    items = _query_unprocessed(cfg, _MAX_BATCH)
    if not items:
        return 0

    now = int(time.time())
    dicts = [fetch_and_cache(cfg, _item_to_dict(it)) for it in items]
    to_write, to_mark = [], []
    for d in dicts:
        failed = d.pop("_fetch_failed", False)
        if failed and (now - int(d.get("received_at", 0) or 0)) < _FETCH_GIVEUP_SEC:
            continue  # transient failure: leave unprocessed so the next poll retries
        to_write.append(d)
        if d["message_id"]:
            to_mark.append(d["message_id"])

    if to_write:
        path = Path(cfg.inbox_jsonl)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Hold a sidecar lock across the append so the hook's rename-based drain
        # (which ignores flock on the inbox inode) cannot interleave mid-write.
        lock_path = str(path) + ".lock"
        with open(lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                with path.open("a", encoding="utf-8") as f:
                    for d in to_write:
                        f.write(json.dumps(d, ensure_ascii=False) + "\n")
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    if to_mark:
        _mark_processed(cfg, to_mark)
    return len(to_write)


def main() -> None:
    """Entry point for the ``line-inbox-poll`` script (cron)."""
    cfg = Config.from_env()
    if not cfg.can_poll:
        print("LINE_INBOX_TABLE not set; nothing to poll")
        return
    n = drain(cfg)
    if n:
        print(f"drained {n} message(s) to {cfg.inbox_jsonl}")
