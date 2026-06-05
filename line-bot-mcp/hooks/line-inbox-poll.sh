#!/usr/bin/env bash
# cron wrapper: poll the DynamoDB inbox into ~/.claude/line_inbox.jsonl.
# Uses the package venv's boto3 (the system python3 has none).
#
# Install in crontab (every 2 minutes):
#   */2 * * * * /path/to/embodied-claude-additional-mcps/line-bot-mcp/hooks/line-inbox-poll.sh >> /tmp/line-inbox-poll.log 2>&1

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd /path/to/embodied-claude-additional-mcps || exit 0
exec uv run --directory line-bot-mcp line-inbox-poll
