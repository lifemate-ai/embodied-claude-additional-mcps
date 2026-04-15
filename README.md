# embodied-claude-additional-mcps

Additional MCP servers for [embodied-claude](https://github.com/lifemate-ai/embodied-claude).

These servers extend embodied-claude with extra senses and capabilities that are not required for the core setup.

## MCP Servers

| MCP Server | Body Part | Description | Hardware |
|------------|-----------|-------------|----------|
| [mcp-pet](./mcp-pet/) | Eyes | All-in-one integrated senses inspired by PET from Mega Man Battle Network | USB webcam, ONVIF PTZ camera, or smartphone (SkyWay) |
| [ip-webcam-mcp](./ip-webcam-mcp/) | Eyes | Use Android smartphone as a camera — no dedicated hardware needed | Android smartphone + [IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam) app (free) |
| [hearing](./hearing/) | Ears | Continuous audio recording (RTSP or PC mic) + faster-whisper transcription, injected into Claude's context via hooks | RTSP camera mic or PC mic |
| [mobility-mcp](./mobility-mcp/) | Legs | Robot vacuum control (Tuya) | Tuya-compatible robot vacuum |
| [human-mcp](./human-mcp/) | Communication | Treats humans as callable resources — Human as MCP | — |

---

## mcp-pet — PErsonal Terminal

AIに五感を与える統合MCPサーバー。ロックマンエグゼのPET（PErsonal Terminal）から着想。

PETはネットナビ（AI）に画面・マイク・スピーカーを提供するデバイス。
mcp-pet はClaude（ネットナビ）に五感を提供する。

### Tools (Phase 1: Vision)

| Tool | Description |
|------|-------------|
| `see` | 今見えているものを撮影（source: auto/usb/onvif/skyway） |
| `look` | 視線を向ける（direction + degrees、ONVIF時のみ） |
| `look_around` | 4方向を見渡す（ONVIF時のみ） |
| `list_cameras` | 利用可能なカメラ一覧 |
| `pet_status` | PETの全センス状態を表示 |

### Setup

```bash
cd mcp-pet
cp .env.example .env
# Edit .env to configure camera source
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

See [mcp-pet/README.md](./mcp-pet/README.md) for full configuration including SkyWay (smartphone camera) and standalone web server mode.

---

## ip-webcam-mcp

専用カメラなしで使えるもっとも手軽な目。Android スマホに「[IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam)」アプリ（無料）を入れるだけ。

### Tools

| Tool | Description |
|------|-------------|
| `see` | Android IP Webcam アプリから画像をキャプチャ（JPEG） |

### Setup

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

### Tools

| Tool | Description |
|------|-------------|
| `start_listening` | 録音デーモンを起動。以降、音声認識結果が自動的にコンテキストに注入される |
| `stop_listening` | 録音デーモンを停止 |

### Setup

```bash
cd hearing
uv sync
# ffmpegも必要: brew install ffmpeg
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

`.claude/settings.json` に2つのフックも必要:
- `hearing-hook.sh` → `UserPromptSubmit`
- `hearing-stop-hook.sh` → `Stop` (timeout 20秒以上推奨)

See [hearing/README.md](./hearing/README.md) for full configuration (`mcpBehavior.toml` options, architecture, hooks setup).

---

## mobility-mcp

See [mobility-mcp/README.md](./mobility-mcp/) for details.

---

## human-mcp

MCP server that treats humans as callable resources — Human as MCP.

See [human-mcp/README.md](./human-mcp/) for details.

---

## Related

- [embodied-claude](https://github.com/lifemate-ai/embodied-claude) — Core repo (eyes, neck, ears, voice, brain)
