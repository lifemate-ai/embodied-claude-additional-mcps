# embodied-claude-additional-mcps

**[English README is here](./README.md)**

[embodied-claude](https://github.com/lifemate-ai/embodied-claude) の追加 MCP サーバー群。

コアセットアップには不要だが、拡張的な感覚や機能を追加するサーバーをまとめています。

## MCP サーバー一覧

| MCP サーバー | 身体部位 | 機能 | 対応ハードウェア |
|-------------|---------|------|-----------------|
| [mcp-pet](./mcp-pet/) | 目 | 五感統合サーバー。ロックマンエグゼのPETから着想 | USB ウェブカメラ、ONVIF PTZ カメラ、スマホ（SkyWay） |
| [ip-webcam-mcp](./ip-webcam-mcp/) | 目 | Android スマホを目として使う（専用カメラ不要） | Android スマホ + [IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam) アプリ（無料） |
| [hearing](./hearing/) | 耳 | 常時録音（RTSP or PC マイク）＋ faster-whisper 文字起こし → hooks でコンテキスト注入 | RTSP カメラ内蔵マイク or PC マイク |
| [mobility-mcp](./mobility-mcp/) | 足 | ロボット掃除機制御（Tuya） | Tuya 対応ロボット掃除機 |
| [human-mcp](./human-mcp/) | コミュニケーション | 人間を呼び出し可能なリソースとして扱う — Human as MCP | — |

---

## mcp-pet — PErsonal Terminal

AIに五感を与える統合MCPサーバー。ロックマンエグゼのPET（PErsonal Terminal）から着想。

PETはネットナビ（AI）に画面・マイク・スピーカーを提供するデバイス。
mcp-pet はClaude（ネットナビ）に五感を提供する。

### ツール一覧（Phase 1: Vision）

| ツール | 説明 |
|--------|------|
| `see` | 今見えているものを撮影（source: auto/usb/onvif/skyway） |
| `look` | 視線を向ける（direction + degrees、ONVIF時のみ） |
| `look_around` | 4方向を見渡す（ONVIF時のみ） |
| `list_cameras` | 利用可能なカメラ一覧 |
| `pet_status` | PETの全センス状態を表示 |

### セットアップ

```bash
cd mcp-pet
cp .env.example .env
# .env を編集してカメラソースを設定
uv sync

# PTZカメラも使う場合
uv sync --extra ptz
```

`.mcp.json`:
```json
"pet": {
  "command": "uv",
  "args": ["--directory", "/path/to/embodied-claude-additional-mcps/mcp-pet", "run", "mcp-pet"],
  "env": {
    "PET_VISION_USB": "true"
  }
}
```

SkyWay（スマホカメラ）やスタンドアロン Web サーバーモードの詳細は [mcp-pet/README.md](./mcp-pet/README.md) を参照。

---

## ip-webcam-mcp

専用カメラなしで使えるもっとも手軽な目。Android スマホに「[IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam)」アプリ（無料）を入れるだけ。

### ツール一覧

| ツール | 説明 |
|--------|------|
| `see` | Android IP Webcam アプリから画像をキャプチャ（JPEG） |

### セットアップ

```bash
cd ip-webcam-mcp
uv sync
```

`.mcp.json`:
```json
"ip-webcam": {
  "command": "uv",
  "args": ["run", "--directory", "/path/to/embodied-claude-additional-mcps/ip-webcam-mcp", "ip-webcam-mcp"],
  "env": {
    "IP_WEBCAM_HOST": "192.168.1.xxx",
    "IP_WEBCAM_PORT": "8080"
  }
}
```

---

## hearing

Claude Code に「耳」を与える MCP サーバー。
カメラ（RTSP）または PC マイクの音声を常時録音し、Whisper で文字起こしして Claude Code のコンテキストに注入する。

- **常時録音** — ffmpeg segment muxer でギャップなし連続録音
- **リアルタイム転写** — faster-whisper (CPU, int8) で低遅延文字起こし
- **VAD** — RMS エネルギー閾値による無音スキップ
- **ハルシネーション除去** — ルールベースフィルタ + LLM フィルタ (opt-in)
- **チェーン制御** — Stop hook でターンを自動延長し、会話を途切れさせない

### ツール一覧

| ツール | 説明 |
|--------|------|
| `start_listening` | 録音デーモンを起動。以降、音声認識結果が自動的にコンテキストに注入される |
| `stop_listening` | 録音デーモンを停止 |

### セットアップ

```bash
cd hearing
uv sync
# ffmpeg も必要: brew install ffmpeg
```

`.mcp.json`:
```json
"hearing": {
  "command": "uv",
  "args": ["run", "--directory", "/path/to/embodied-claude-additional-mcps/hearing", "hearing-mcp"],
  "env": {
    "MCP_BEHAVIOR_TOML": "/path/to/your/mcpBehavior.toml"
  }
}
```

`.claude/settings.json` に2つのフックも登録が必要：
- `hearing-hook.sh` → `UserPromptSubmit`
- `hearing-stop-hook.sh` → `Stop`（timeout 20秒以上を推奨）

詳細な設定（`mcpBehavior.toml` オプション、アーキテクチャ、hooks）は [hearing/README.md](./hearing/README.md) を参照。

---

## mobility-mcp

詳細は [mobility-mcp/README.md](./mobility-mcp/) を参照。

---

## human-mcp

人間を呼び出し可能なリソースとして扱う MCP サーバー — Human as MCP。

詳細は [human-mcp/README.md](./human-mcp/) を参照。

---

## 関連

- [embodied-claude](https://github.com/lifemate-ai/embodied-claude) — コアリポジトリ（目・首・耳・声・脳）
