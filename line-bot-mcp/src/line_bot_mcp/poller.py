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
from pathlib import Path
from typing import Any

from .config import Config

_MAX_BATCH = 50


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
    """Normalise a DynamoDB item (Decimal etc.) into a plain JSON-safe dict."""
    return {
        "message_id": str(item.get("message_id", "")),
        "person": str(item.get("person", "owner")),
        "text": str(item.get("text", "")),
        "line_ts": int(item.get("line_ts", 0) or 0),
        "received_at": int(item.get("received_at", 0) or 0),
    }


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

    dicts = [_item_to_dict(it) for it in items]
    path = Path(cfg.inbox_jsonl)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            for d in dicts:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    _mark_processed(cfg, [d["message_id"] for d in dicts if d["message_id"]])
    return len(dicts)


def main() -> None:
    """Entry point for the ``line-inbox-poll`` script (cron)."""
    cfg = Config.from_env()
    if not cfg.can_poll:
        print("LINE_INBOX_TABLE not set; nothing to poll")
        return
    n = drain(cfg)
    if n:
        print(f"drained {n} message(s) to {cfg.inbox_jsonl}")
