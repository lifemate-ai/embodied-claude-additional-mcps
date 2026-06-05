# Lambda 受信基盤のデプロイ手順（オーナーが手動実行）

LINE webhook を受ける `API Gateway + Lambda + DynamoDB` を AWS SAM で構築する。
AI（実装者）はコードと `template.yaml` までを用意済み。以下はオーナーの手作業。

## 0. 前提
- AWS アカウント（オーナー所有）と `aws configure` 済みの認証情報
- `brew install aws-sam-cli`

## 1. LINE Developers 側の準備（先にやる）
1. [LINE Developers Console](https://developers.line.biz/) でプロバイダー作成
2. **Messaging API チャネル**を作成
3. **Channel secret** を控える（手順3の deploy で使う）
4. **Channel access token (long-lived)** を発行 → the host machine の `line-bot-mcp/.env` の `LINE_CHANNEL_ACCESS_TOKEN` へ
5. 「応答メッセージ」OFF、「Webhook」ON（URL は手順3の後で登録）
6. オーナーのスマホで、この公式アカウントを友だち追加

## 2. ビルド
```bash
cd line-bot-mcp/lambda
sam build
```

## 3. デプロイ
```bash
sam deploy --guided \
  --parameter-overrides "LineChannelSecret=<channel secret>"
```
- stack_name: `line-bot` / region: `ap-northeast-1`
- `CAPABILITY_IAM` を許可
- 完了後、出力 **WebhookUrl**（`https://xxxx.execute-api.ap-northeast-1.amazonaws.com/webhook`）を控える

→ この URL を LINE Developers の **Webhook URL** に登録し、「検証」ボタンで疎通確認。

## 4. the owner の userId を確定
1. スマホから公式アカウントに何かメッセージを送る
2. CloudWatch Logs（`/aws/lambda/line-webhook`）で `source.userId`（`U...`）を確認
   - ※ LINE プロフィール画面に出る ID とは別物。必ず webhook ログのものを使う
3. その userId を 2 箇所へ:
   - Lambda 環境変数: `sam deploy --parameter-overrides "LineChannelSecret=... LineOwnerUserId=Uxxxx"` で再デプロイ
   - the host machine の `line-bot-mcp/.env` の `LINE_OWNER_USER_ID`

## 5. ポーラー用 IAM ユーザー（最小権限）
1. IAM ユーザー `line-poller` を作成（プログラムアクセス）
2. 以下のインラインポリシーを付与（`<ACCT>` は自分のアカウントID）:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:Query"],
      "Resource": "arn:aws:dynamodb:ap-northeast-1:<ACCT>:table/line-inbox/index/unprocessed-index"
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:UpdateItem", "dynamodb:GetItem"],
      "Resource": "arn:aws:dynamodb:ap-northeast-1:<ACCT>:table/line-inbox"
    }
  ]
}
```
3. アクセスキーを発行し、the host machine の `line-bot-mcp/.env` の
   `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` に記入

## 6. 更新・削除
- 更新: `sam build && sam deploy`
- 削除: `sam delete --stack-name line-bot`

## メモ
- 現状 secret は Lambda 環境変数。将来は SSM Parameter Store / Secrets Manager 推奨。
- メッセージは DynamoDB TTL（既定14日）で自動失効。
