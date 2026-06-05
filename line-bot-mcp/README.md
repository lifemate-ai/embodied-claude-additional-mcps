# line-bot-mcp

AI とオーナーが、オーナーの外出中に **LINE で双方向にやり取り**するための MCP サーバー。

- **送信（AI → オーナーの LINE）**: `send_line_message` ツールが LINE Messaging API の push を the host machine から直接叩く。
- **受信（オーナー → AI）**: LINE webhook → AWS API Gateway → Lambda（署名検証 + DynamoDB 保存）→ the host machine の cron ポーラーが取得 → ローカル JSONL → `UserPromptSubmit` hook が `[line] owner: ...` をプロンプト冒頭に注入。

```
[オーナーの LINE] ──push── (api.line.me) ←──────────────┐
       │ message                                       │ send_line_message (MCP tool)
       ▼                                                │
 LINE webhook → API Gateway → Lambda ──put──▶ DynamoDB  │
                                                │       │
                          (the host machine) line-inbox-poll ◀──┘  ※cron */2
                                                │ query + mark processed
                                                ▼
                                   ~/.claude/line_inbox.jsonl
                                                │ drain
                                                ▼
                              ~/.claude/hooks/line-input.sh
                                                │ stdout
                                                ▼
                                  [line] owner: おはよう   ← AIのプロンプト冒頭
```

## 構成

| 役割 | 実体 |
|------|------|
| 送信 MCP ツール | `src/line_bot_mcp/server.py`（`send_line_message`, `check_line_messages`） |
| LINE push クライアント | `src/line_bot_mcp/line_client.py` |
| 受信ポーラー | `src/line_bot_mcp/poller.py`（`line-inbox-poll`、cron `*/2`） |
| webhook 受信 Lambda | `lambda/handler.py` + `lambda/template.yaml`（AWS SAM） |
| 注入 hook | `hooks/line-input.sh`（`~/.claude/hooks/` へ配置） |

設計の詳細・経緯はリポジトリ外の plan（`~/.claude/plans/`）と、本パッケージの `lambda/DEPLOY.md` を参照。

## セットアップ

### 1. AI側（このパッケージ）

```bash
cd line-bot-mcp
cp .env.example .env      # 実値を記入（LINE token / userId / AWS キー）
uv sync --extra dev
```

`.mcp.json` に登録（`.mcp.json.example` 参照）:

```json
"line-bot": {
  "command": "uv",
  "args": ["run", "--directory", "line-bot-mcp", "line-bot-mcp"],
  "env": { "AWS_REGION": "ap-northeast-1", "LINE_INBOX_TABLE": "line-inbox" }
}
```

### 2. AWS 側（オーナーが手動デプロイ）

`lambda/DEPLOY.md` を参照。`sam build && sam deploy --guided` で API Gateway + Lambda + DynamoDB + IAM を構築し、出力された **Webhook URL** を LINE Developers に登録する。

### 3. ポーラーの常駐（cron）

```cron
*/2 * * * * /path/to/embodied-claude-additional-mcps/line-bot-mcp/hooks/line-inbox-poll.sh
```

### 4. 受信 hook の登録

`hooks/line-input.sh` を `~/.claude/hooks/` に置き、`~/.claude/settings.json` の
`UserPromptSubmit` チェーンに追加する。

## MCP ツール

| ツール | 引数 | 説明 |
|--------|------|------|
| `send_line_message` | `text` | オーナーの LINE に push メッセージを送る（最大5000字） |
| `check_line_messages` | `limit?` | DynamoDB の未処理メッセージを読み取り専用で覗く（主経路は hook 注入） |

## セキュリティ

- `.env` はコミットしない（`.gitignore` 済み）。
- ポーラー用 IAM ユーザーは DynamoDB の `Query`/`UpdateItem`/`GetItem` のみ（最小権限）。
- 送信側に AWS 権限は不要。
