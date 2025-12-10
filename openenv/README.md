# OpenEnv - Wine Environment

OpenEnv-compatible Docker environment for running and controlling Windows applications via standardized HTTP API. Designed for reinforcement learning agents to interact with Windows applications through Wine. Upstream OpenEnv project: https://github.com/meta-pytorch/OpenEnv.

## Overview

OpenEnv provides a unified interface for RL environments. This implementation wraps Windows applications running in Wine, exposing them through the standard OpenEnv HTTP API:

- **`POST /reset`** - Reset environment, return initial observation
- **`POST /step`** - Execute action, return observation
- **`GET /state`** - Get current environment state
- **`GET /health`** - Health check

This enables RL agents to train on Windows applications using the same interface as any other OpenEnv environment.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design and RL integration.

```
┌─────────────────────────────────────────────────────────────┐
│                     RL Training Loop                        │
│   agent.act(obs) → action → env.step(action) → obs, reward  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    OpenEnv HTTP Client                      │
│              POST /step {"action": {...}}                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Docker Container                          │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   FastAPI   │──│ syncinput.exe│──│  Wine + Notepad  │   │
│  │   Server    │  │  (TCP:9090)  │  │   (Display :99)  │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│        │                                     │              │
│        └──────── FFmpeg Screen Capture ──────┘              │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
cd /home/giongto/code/cloud-morph/openenv
./run.sh
```

Open **http://localhost:8000/viewer** to see the live stream.

## API Reference

### POST /reset

Reset environment to initial state.

**Request:**
```json
{}
```

**Response:**
```json
{
  "observation": {
    "screen": "<base64_jpeg>",
    "screen_shape": [600, 800, 3],
    "metadata": {}
  },
  "reward": null,
  "done": false
}
```

### POST /step

Execute an action and return new observation.

**Keyboard Action:**
```json
{
  "action_type": "key",
  "key": 65,
  "key_state": "down"
}
```

**Mouse Action:**
```json
{
  "action_type": "mouse",
  "button": "left",
  "mouse_state": "down",
  "x": 0.5,
  "y": 0.5
}
```

**Response:** Same as `/reset`

### GET /state

Get current environment state (without screen capture).

```json
{
  "episode_id": 1,
  "step_count": 42,
  "app_file": "notepad",
  "window_title": "Notepad",
  "screen_width": 800,
  "screen_height": 600
}
```

### GET /health

```json
{"status": "healthy"}
```

### GET /stream

MJPEG live stream (~10 FPS) for debugging/visualization.

### GET /viewer

HTML page with embedded stream viewer.

## Key Codes

| Key | Code | Key | Code |
|-----|------|-----|------|
| A-Z | 65-90 | 0-9 | 48-57 |
| Enter | 13 | Space | 32 |
| Backspace | 8 | Tab | 9 |
| ← | 37 | ↑ | 38 |
| → | 39 | ↓ | 40 |

## Python Client Example

```python
import requests
import base64
import numpy as np
from PIL import Image
from io import BytesIO

class OpenEnvClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
    
    def reset(self):
        resp = requests.post(f"{self.base_url}/reset")
        return self._parse_observation(resp.json())
    
    def step(self, action):
        resp = requests.post(f"{self.base_url}/step", json=action)
        return self._parse_observation(resp.json())
    
    def _parse_observation(self, data):
        screen_b64 = data["observation"]["screen"]
        screen_bytes = base64.b64decode(screen_b64)
        image = Image.open(BytesIO(screen_bytes))
        return np.array(image)

# Usage
env = OpenEnvClient()
obs = env.reset()

# Type "HELLO"
for key in [72, 69, 76, 76, 79]:
    obs = env.step({"action_type": "key", "key": key, "key_state": "down"})

print(f"Screen shape: {obs.shape}")
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `SCREEN_WIDTH` | 800 | Virtual screen width |
| `SCREEN_HEIGHT` | 600 | Virtual screen height |
| `APP_FILE` | notepad | Wine application to run |
| `WINDOW_TITLE` | Notepad | Window title for input targeting |

## Manual Commands

```bash
# Build
docker build -t openenv .

# Run
docker run -d --name openenv \
  -p 8000:8000 -p 9090:9090 \
  -e SCREEN_WIDTH=800 \
  -e SCREEN_HEIGHT=600 \
  -e APP_FILE=notepad \
  -e WINDOW_TITLE="Notepad" \
  openenv

# Check status
docker exec openenv supervisorctl -s http://127.0.0.1:9001 status

# View logs
docker exec openenv cat /app/logs/syncinput.log

# Stop
docker stop openenv && docker rm openenv
```

## Directory Structure

```
openenv/
├── Dockerfile              # Container definition
├── README.md               # This file
├── ARCHITECTURE.md         # Design and RL integration
├── run.sh                  # Quick start script
├── config/
│   └── supervisord.conf    # Process management
├── scripts/
│   ├── download_gecko_and_mono.sh
│   └── start_syncinput.sh  # Connection wait wrapper
└── src/
    ├── syncinput.cpp       # Input injection (Windows)
    ├── models.py           # Data models
    └── server/
        ├── app.py          # FastAPI HTTP server
        └── wine_environment.py  # Environment implementation
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| wineapp FATAL | Check `/app/logs/wineapp.log` - DISPLAY or app issue |
| syncinput not connecting | Check `/app/logs/syncinput.log` - should show "Connected!" |
| Black screen | Xvfb may not be running, check `supervisorctl status` |
| Missing keys | First key after 10s idle may reconnect, retry logic handles this |

## License

Based on cloud-morph Wine architecture. OpenEnv interface compatible.
