"""LINE BOT MCP — two-way LINE messaging between an AI and its owner.

- Outbound (AI -> owner): ``send_line_message`` MCP tool calls the LINE
  Messaging API push endpoint directly from the the host machine.
- Inbound (owner -> AI): an AWS Lambda receives the LINE webhook, stores
  the message in DynamoDB, a cron poller drains it into a local JSONL file, and
  a ``UserPromptSubmit`` hook injects ``[line] owner: ...`` into the prompt.
"""

__version__ = "0.1.0"
