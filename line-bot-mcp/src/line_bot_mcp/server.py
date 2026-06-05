"""LINE BOT MCP server.

Exposes two tools:
- ``send_line_message``: push a message to Kouta's LINE (outbound).
- ``check_line_messages``: read-only peek at unprocessed inbound messages
  (the main inbound path is the hook injection, not this tool).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import line_client
from .config import Config

mcp = FastMCP("line-bot")

MAX_LEN = 5000


@mcp.tool()
def send_line_message(text: str) -> str:
    """コウタの LINE に push メッセージを送る（ここね能動発信）。

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
        return "Error: LINE_CHANNEL_ACCESS_TOKEN or LINE_KOUTA_USER_ID not set"
    try:
        line_client.push(cfg.channel_access_token, cfg.kouta_user_id, text)
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


def main() -> None:
    """Entry point for the ``line-bot-mcp`` script."""
    mcp.run()
