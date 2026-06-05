"""LINE webhook receiver Lambda.

Verifies the X-Line-Signature against the channel secret, then stores each
text message in DynamoDB with a conditional put (idempotent against LINE's
webhook redelivery). Always returns 200 quickly so LINE does not retry.

Runtime: python3.12 (boto3/botocore are provided by the Lambda runtime).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import boto3
from botocore.exceptions import ClientError

_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
_OWNER_USER_ID = os.environ.get("LINE_OWNER_USER_ID", "")
_TABLE_NAME = os.environ.get("INBOX_TABLE", "")
_TTL_DAYS = int(os.environ.get("INBOX_TTL_DAYS", "14"))

_dynamodb = None


def _table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(_TABLE_NAME)


def verify_signature(body_bytes: bytes, signature: str) -> bool:
    """Constant-time compare of the base64 HMAC-SHA256 of the raw body."""
    mac = hmac.new(_CHANNEL_SECRET.encode("utf-8"), body_bytes, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature or "")


def _raw_body(event: dict) -> bytes:
    """Return the raw request body bytes (signature must use raw bytes)."""
    body = event.get("body", "") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def _store_event(ev: dict, now: int) -> None:
    msg = ev.get("message", {})
    if msg.get("type") != "text":
        return
    message_id = msg.get("id")
    if not message_id:
        return
    user_id = (ev.get("source") or {}).get("userId", "")
    person = "owner" if user_id and user_id == _OWNER_USER_ID else "unknown"
    try:
        _table().put_item(
            Item={
                "message_id": message_id,
                "person": person,
                "text": msg.get("text", ""),
                "line_ts": int(ev.get("timestamp", now * 1000)),
                "received_at": now,
                "processed": 0,
                "ttl": now + _TTL_DAYS * 86400,
            },
            ConditionExpression="attribute_not_exists(message_id)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # duplicate webhook redelivery — already stored, ignore


def handler(event, context):  # noqa: ANN001, ARG001 - Lambda signature
    headers = event.get("headers") or {}
    signature = headers.get("x-line-signature") or headers.get("X-Line-Signature", "")
    body_bytes = _raw_body(event)

    if not verify_signature(body_bytes, signature):
        return {"statusCode": 403, "body": "invalid signature"}

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"statusCode": 200, "body": "ok"}

    now = int(time.time())
    for ev in payload.get("events", []):
        if ev.get("type") == "message":
            _store_event(ev, now)

    return {"statusCode": 200, "body": "ok"}
