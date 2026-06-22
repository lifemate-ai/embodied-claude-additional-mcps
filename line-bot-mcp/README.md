# line-bot-mcp

AI とオーナーが、オーナーの外出中に **LINE で双方向にやり取り**するための MCP サーバー。テキストに加え、**画像・音声**も双方向で送受信できる。

- **送信（AI → オーナーの LINE）**: `send_line_message`（テキスト）／`send_line_image`（画像）／`send_line_audio`（音声）。テキストは Messaging API push を the host machine から直接叩く。画像/音声は ffmpeg で整形 → S3 にアップロード → presigned URL で push する。
- **受信（オーナー → AI）**: LINE webhook → AWS API Gateway → Lambda（署名検証 + DynamoDB 保存）→ the host machine の cron ポーラーが取得 → ローカル JSONL → `UserPromptSubmit` hook がプロンプト冒頭に注入。画像/音声は本体をポーラーが取得してローカル保存し、音声は faster-whisper で文字起こしして注入する（画像は `fetch_line_image` で閲覧）。

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
| 送受信 MCP ツール | `src/line_bot_mcp/server.py`（`send_line_message`, `send_line_image`, `send_line_audio`, `fetch_line_image`, `check_line_messages`） |
| LINE push/content クライアント | `src/line_bot_mcp/line_client.py` |
| メディア整形・S3 配信 | `src/line_bot_mcp/media.py`（ffmpeg + presigned URL） |
| 受信ポーラー | `src/line_bot_mcp/poller.py`（`line-inbox-poll`、cron `*/2`、メディア取得・文字起こし） |
| webhook 受信 Lambda | `lambda/handler.py` + `lambda/template.yaml`（AWS SAM、S3 バケット込み） |
| 注入 hook | `hooks/line-input.sh`（`~/.claude/hooks/` へ配置） |

設計の詳細・経緯はリポジトリ外の plan（`~/.claude/plans/`）と、本パッケージの `lambda/DEPLOY.md` を参照。

## セットアップ

### 1. AI側（このパッケージ）

```bash
cd line-bot-mcp
cp .env.example .env      # 実値を記入（LINE token / userId / AWS キー / S3 バケット）
uv sync --extra dev
```

- **画像/音声の送信**には `ffmpeg`/`ffprobe` が必要（`brew install ffmpeg` 等）。
- **音声受信の文字起こし**を使うなら `uv sync --extra transcribe`（faster-whisper）。未導入なら音声は保存のみ。

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
| `send_line_image` | `image_path` | 画像を送る（JPEG/PNG、最大10MB。プレビューは自動縮小） |
| `send_line_audio` | `audio_path` | 音声を送る（m4a に自動変換、最大1分） |
| `fetch_line_image` | `ref` | 受信画像を取得して表示（ポーラーが保存したローカルパス、または message_id） |
| `check_line_messages` | `limit?` | DynamoDB の未処理メッセージを読み取り専用で覗く（主経路は hook 注入） |

## セキュリティ

- `.env` はコミットしない（`.gitignore` 済み）。
- ポーラー兼メディア送信用 IAM ユーザーは、DynamoDB の `Query`/`UpdateItem`/`GetItem` と S3 の `PutObject`/`GetObject`（`media/*` 限定）のみ（最小権限）。
- メディア送信を使わないなら S3 権限は不要（テキストのみで動作）。
- S3 バケットは private（PublicAccessBlock 全 ON・ACL 無効）。配信は短命の presigned GET URL（既定15分）のみで、公開設定は一切しない。受信メディアの取得は owner からのものに限定（第三者の連投による取得コストを防ぐ）。
