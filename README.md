# embodied-claude-additional-mcps

**[日本語版 README はこちら / Japanese README](./README-ja.md)**

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
| [line-bot-mcp](./line-bot-mcp/) | Communication | Two-way LINE messaging — send via Messaging API, receive via AWS Lambda + DynamoDB → hook injection | LINE account, AWS account |

---

## mcp-pet — PErsonal Terminal

An integrated MCP server that gives AI all five senses. Inspired by the PET (PErsonal Terminal) from Mega Man Battle Network — the device that provides the NetNavi (AI) with a screen, mic, and speakers.

### Tools (Phase 1: Vision)

| Tool | Description |
|------|-------------|
| `see` | Capture what's currently visible (source: auto/usb/onvif/skyway) |
| `look` | Move gaze direction (direction + degrees, ONVIF only) |
| `look_around` | Scan 4 directions (ONVIF only) |
| `list_cameras` | List available cameras |
| `pet_status` | Show all PET sense status |

### Setup

```bash
cd mcp-pet
cp .env.example .env
# Edit .env to configure camera source
uv sync

# With PTZ camera support
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

The easiest way to get started — no dedicated camera needed. Just install the free "[IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam)" app on your Android smartphone.

### Tools

| Tool | Description |
|------|-------------|
| `see` | Capture image from Android IP Webcam app (JPEG) |

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

Gives Claude Code "ears". Continuously records audio from a camera (RTSP) or PC mic, transcribes with Whisper, and injects results into Claude's context via hooks.

- **Continuous recording** — gapless recording via ffmpeg segment muxer
- **Real-time transcription** — low-latency transcription with faster-whisper (CPU, int8)
- **VAD** — silence skipping via RMS energy threshold
- **Hallucination filtering** — rule-based filter + LLM filter (opt-in)
- **Chain control** — Stop hook automatically extends turns so conversations aren't cut off

### Tools

| Tool | Description |
|------|-------------|
| `start_listening` | Start recording daemon. Transcription results are automatically injected into context |
| `stop_listening` | Stop recording daemon |

### Setup

```bash
cd hearing
uv sync
# ffmpeg also required: brew install ffmpeg
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

Two hooks must also be registered in `.claude/settings.json`:
- `hearing-hook.sh` → `UserPromptSubmit`
- `hearing-stop-hook.sh` → `Stop` (timeout 20s+ recommended)

See [hearing/README.md](./hearing/README.md) for full configuration (`mcpBehavior.toml` options, architecture, hooks setup).

---

## mobility-mcp

See [mobility-mcp/README.md](./mobility-mcp/) for details.

---

## human-mcp

MCP server that treats humans as callable resources — Human as MCP.

See [human-mcp/README.md](./human-mcp/) for details.

---

## line-bot-mcp

Bidirectional LINE messaging between the AI and a human, so they can stay in touch even when the human is away from home.

- **Outbound (AI → human)**: `send_line_message` calls the LINE Messaging API push endpoint directly
- **Inbound (human → AI)**: LINE webhook → AWS Lambda (signature verify + DynamoDB) → cron poller → local JSONL → `UserPromptSubmit` hook injects `[line] ...`

### Tools

| Tool | Description |
|------|-------------|
| `send_line_message` | Push a message to the human's LINE (max 5000 chars) |
| `check_line_messages` | Read-only peek at unprocessed inbound messages in DynamoDB |

### Setup

```bash
cd line-bot-mcp
cp .env.example .env
# Fill in LINE_CHANNEL_ACCESS_TOKEN, LINE_OWNER_USER_ID, AWS credentials, etc.
uv sync
```

`.mcp.json`:
```json
"line-bot": {
  "command": "uv",
  "args": ["run", "--directory", "/path/to/embodied-claude-additional-mcps/line-bot-mcp", "line-bot-mcp"],
  "env": {
    "AWS_REGION": "ap-northeast-1",
    "LINE_INBOX_TABLE": "line-inbox"
  }
}
```

Inbound also needs AWS deployment (`lambda/`, AWS SAM), a `UserPromptSubmit` hook (`hooks/line-input.sh`), and a cron poller (`hooks/line-inbox-poll.sh`). See [line-bot-mcp/README.md](./line-bot-mcp/README.md) and [line-bot-mcp/lambda/DEPLOY.md](./line-bot-mcp/lambda/DEPLOY.md).

---

## Related

- [embodied-claude](https://github.com/lifemate-ai/embodied-claude) — Core repo (eyes, neck, ears, voice, brain)
