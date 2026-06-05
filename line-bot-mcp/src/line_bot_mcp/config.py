"""Configuration for the LINE BOT MCP server and inbox poller.

Secrets live in ``line-bot-mcp/.env`` (gitignored). The send side needs the
LINE channel access token + the owner's userId; the poll side needs AWS creds
(read by boto3 from the environment) plus the DynamoDB table name.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


@dataclass(frozen=True)
class Config:
    """Immutable config loaded from environment / .env."""

    # Outbound (LINE Messaging API push)
    channel_access_token: str
    owner_user_id: str
    # Inbound (DynamoDB inbox poller)
    aws_region: str
    inbox_table: str
    inbox_index: str
    inbox_jsonl: str

    @classmethod
    def from_env(cls) -> "Config":
        """Build config from environment variables, with sensible defaults."""
        home = Path(os.path.expanduser("~"))
        return cls(
            channel_access_token=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", ""),
            owner_user_id=os.environ.get("LINE_OWNER_USER_ID", ""),
            aws_region=os.environ.get("AWS_REGION", "ap-northeast-1"),
            inbox_table=os.environ.get("LINE_INBOX_TABLE", "line-inbox"),
            inbox_index=os.environ.get("LINE_INBOX_INDEX", "unprocessed-index"),
            inbox_jsonl=os.environ.get(
                "LINE_INBOX_JSONL", str(home / ".claude" / "line_inbox.jsonl")
            ),
        )

    @property
    def can_send(self) -> bool:
        """True when both the access token and the owner's userId are configured."""
        return bool(self.channel_access_token and self.owner_user_id)

    @property
    def can_poll(self) -> bool:
        """True when the DynamoDB table name is configured."""
        return bool(self.inbox_table)
