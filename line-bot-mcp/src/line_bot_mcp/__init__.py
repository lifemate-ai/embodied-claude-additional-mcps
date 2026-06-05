"""LINE BOT MCP — two-way LINE messaging between Kokone and Kouta.

- Outbound (Kokone -> Kouta): ``send_line_message`` MCP tool calls the LINE
  Messaging API push endpoint directly from the Mac Mini.
- Inbound (Kouta -> Kokone): an AWS Lambda receives the LINE webhook, stores
  the message in DynamoDB, a cron poller drains it into a local JSONL file, and
  a ``UserPromptSubmit`` hook injects ``[line] kouta: ...`` into the prompt.
"""

__version__ = "0.1.0"
