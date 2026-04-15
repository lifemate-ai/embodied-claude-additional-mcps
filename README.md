# embodied-claude-additional-mcps

Additional MCP servers for [embodied-claude](https://github.com/lifemate-ai/embodied-claude).

These servers extend embodied-claude with extra senses and capabilities that are not required for the core setup.

## MCP Servers

| MCP Server | Body Part | Description | Hardware |
|------------|-----------|-------------|----------|
| [mcp-pet](./mcp-pet/) | Eyes + Voice | All-in-one integrated senses (USB/ONVIF/SkyWay) — inspired by PET from Mega Man Battle Network | Smartphone camera or ONVIF camera |
| [ip-webcam-mcp](./ip-webcam-mcp/) | Eyes | Use Android smartphone as a camera — no dedicated hardware needed | Android smartphone + [IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam) app (free) |
| [hearing](./hearing/) | Ears | Continuous audio recording via RTSP or PC mic + Whisper transcription | RTSP camera mic or PC mic |
| [mobility-mcp](./mobility-mcp/) | Legs | Robot vacuum control (Tuya) | Tuya-compatible robot vacuum |
| [human-mcp](./human-mcp/) | Communication | Treats humans as callable resources — Human as MCP | — |

## Setup

Each server is independent. Install only what you need:

```bash
cd <server-name>
uv sync
```

See each server's README for full configuration details.

### ip-webcam-mcp (Android Smartphone)

```bash
cd ip-webcam-mcp
uv sync
```

Add to `.mcp.json`:
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

### hearing

```bash
cd hearing
uv sync
```

Add to `.mcp.json`:
```json
"hearing": {
  "command": "uv",
  "args": ["run", "--directory", "/path/to/embodied-claude-additional-mcps/hearing", "hearing-mcp"],
  "env": {
    "MCP_BEHAVIOR_TOML": "/path/to/your/mcpBehavior.toml"
  }
}
```

### mcp-pet

```bash
cd mcp-pet
cp .env.example .env
# Edit .env to configure camera source
uv sync
```

## Tools

### ip-webcam-mcp

| Tool | Description |
|------|-------------|
| `see` | Capture snapshot from Android IP Webcam app |

### hearing

| Tool | Description |
|------|-------------|
| `start_listening` | Start continuous audio capture |
| `stop_listening` | Stop audio capture |
| `get_transcript` | Get latest transcription |

### mcp-pet

| Tool | Description |
|------|-------------|
| `see` | Capture image (source: auto/usb/onvif/skyway) |
| `look` | Move camera direction (ONVIF only) |
| `look_around` | Scan 4 directions (ONVIF only) |
| `list_cameras` | List available cameras |
| `pet_status` | Show all sense status |

### mobility-mcp

| Tool | Description |
|------|-------------|
| `start_cleaning` | Start robot vacuum |
| `stop_cleaning` | Stop robot vacuum |
| `return_to_dock` | Send vacuum to dock |
| `move_forward` / `move_backward` | Move in direction |
| `turn_left` / `turn_right` | Rotate |
| `body_status` | Get vacuum status |

### human-mcp

| Tool | Description |
|------|-------------|
| `notify_human` | Send notification to human |
| `request_human` | Request action from human |

## Related

- [embodied-claude](https://github.com/lifemate-ai/embodied-claude) — Core repo (eyes, neck, ears, voice, brain)

