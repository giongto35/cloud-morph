# Bomberman Environment Guide

This guide explains how to run and use the Bomberman game environment with OpenEnv.

## Overview

Bomberman runs via Wine using the Mednafen emulator (PC Engine/TurboGrafx-16). The environment provides:
- HTTP API for controlling the game
- Screen capture and streaming
- Input injection (keyboard controls)
- Audio support via PulseAudio

## Prerequisites

- Docker installed and running
- Python 3.6+ (for the random agent)
- `requests` Python library: `pip install requests`

## Quick Start

### 1. Start the Bomberman Environment

```bash
cd openenv/bomberman
./run_bomberman.sh
```

This will:
- Build the Docker image (if needed)
- Start a container with Bomberman
- Expose the API on `http://localhost:8000`
- Mount the games directory

### 2. Verify It's Running

Check the service status:
```bash
docker exec openenv-bomberman supervisorctl -s http://127.0.0.1:9001 status
```

All services should show `RUNNING`:
- `http_server` - API server
- `pulseaudio` - Audio service
- `syncinput` - Input handler
- `wineapp` - Bomberman game
- `xvfb` - Virtual display

### 3. View the Game

Open in your browser:
- **Viewer**: http://localhost:8000/viewer
- **Stream**: http://localhost:8000/stream

## Game Controls

Bomberman uses the following controls:
- **Arrow Keys** (37=Left, 38=Up, 39=Right, 40=Down) - Move character
- **Enter** (13) - Start/Select/Action button

**Note**: The first time you play, use `Alt+Shift+1` to configure the buttons in Mednafen.

## Using the API

### Reset Environment

```bash
curl -X POST http://localhost:8000/reset
```

### Send Actions

**Arrow Key (Right):**
```bash
curl -X POST http://localhost:8000/step \
  -H 'Content-Type: application/json' \
  -d '{"action": {"action_type": "key", "key": 39, "key_state": "down"}}'
```

**Arrow Key (Up):**
```bash
curl -X POST http://localhost:8000/step \
  -H 'Content-Type: application/json' \
  -d '{"action": {"action_type": "key", "key": 38, "key_state": "down"}}'
```

**Enter Key:**
```bash
curl -X POST http://localhost:8000/step \
  -H 'Content-Type: application/json' \
  -d '{"action": {"action_type": "key", "key": 13, "key_state": "down"}}'
```

### Get Environment State

```bash
curl http://localhost:8000/state
```

### Health Check

```bash
curl http://localhost:8000/health
```

## Random Agent

A random agent script is included to demonstrate API usage:

```bash
python3 random_bomberman_agent.py --base http://localhost:8000 --steps 200 --delay 0.2
```

**Options:**
- `--base`: OpenEnv API base URL (default: `http://localhost:8000`)
- `--steps`: Number of random actions to send (default: `200`)
- `--delay`: Delay between actions in seconds (default: `0.2`)

The agent will:
1. Reset the environment
2. Send random arrow key and Enter key actions
3. Print progress for each action

## Configuration

### Screen Resolution

Set custom screen dimensions:
```bash
SCREEN_WIDTH=1024 SCREEN_HEIGHT=768 ./run_bomberman.sh
```

### Ports

Default ports:
- `8000` - HTTP API
- `9090` - Input socket

To use different ports, modify `run_bomberman.sh`:
```bash
docker run -d --name $CONTAINER_NAME \
  -p 8001:8000 \  # Change host port
  -p 9091:9090 \  # Change host port
  ...
```

## Troubleshooting

### Check Logs

**Wine/Game Logs:**
```bash
docker exec openenv-bomberman cat /app/logs/wineapp.log
```

**Input Handler Logs:**
```bash
docker exec openenv-bomberman cat /app/logs/syncinput.log
```

**PulseAudio Logs:**
```bash
docker exec openenv-bomberman cat /app/logs/pulseaudio.log
```

**HTTP Server Logs:**
```bash
docker exec openenv-bomberman cat /app/logs/http_server.log
```

### Common Issues

**Port Already in Use:**
```bash
# Stop existing container
docker stop openenv-bomberman
docker rm openenv-bomberman
```

**Game Not Starting:**
- Check `wineapp.log` for errors
- Verify game files exist in `games/Bomberman/med/`
- Ensure `mednafen.exe` and `game.pce` are present

**Audio Issues:**
- Check `pulseaudio.log` for errors
- Verify PulseAudio service is running
- Audio may not work in headless environments

**Input Not Working:**
- Check `syncinput.log` for connection issues
- Verify window title matches "Mednafen"
- Ensure syncinput service is running

### Restart Services

Restart individual services:
```bash
docker exec openenv-bomberman supervisorctl -s http://127.0.0.1:9001 restart wineapp
docker exec openenv-bomberman supervisorctl -s http://127.0.0.1:9001 restart syncinput
```

## Stopping the Environment

```bash
docker stop openenv-bomberman
docker rm openenv-bomberman
```

## File Structure

```
bomberman/
├── README.md                    # This file
├── run_bomberman.sh            # Script to start Bomberman environment
└── random_bomberman_agent.py   # Random agent example

../games/Bomberman/             # Game files (mounted into container)
├── med/
│   ├── mednafen.exe           # Emulator executable
│   └── game.pce               # Game ROM
└── Bomberman.bat              # Original launcher script
```

## API Reference

### POST /reset
Reset the environment to initial state.

**Response:**
```json
{
  "observation": {
    "screen": "<base64_encoded_image>",
    "screen_shape": [600, 800, 3],
    "metadata": {}
  },
  "reward": null,
  "done": false
}
```

### POST /step
Execute an action in the environment.

**Request:**
```json
{
  "action": {
    "action_type": "key",
    "key": 39,
    "key_state": "down"
  }
}
```

**Response:**
```json
{
  "observation": {
    "screen": "<base64_encoded_image>",
    "screen_shape": [600, 800, 3],
    "metadata": {}
  },
  "reward": null,
  "done": false
}
```

### GET /state
Get current environment state.

**Response:**
```json
{
  "episode_id": 1,
  "step_count": 42,
  "app_file": "/games/Bomberman/med/mednafen.exe",
  "window_title": "Mednafen",
  "screen_width": 800,
  "screen_height": 600
}
```

### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy"
}
```

### GET /viewer
HTML viewer page with live stream.

### GET /stream
MJPEG stream endpoint for real-time viewing.

## Key Codes Reference

| Key | Code | Description |
|-----|------|-------------|
| Left Arrow | 37 | Move left |
| Up Arrow | 38 | Move up |
| Right Arrow | 39 | Move right |
| Down Arrow | 40 | Move down |
| Enter | 13 | Start/Select/Action |

## Examples

### Python Client Example

```python
import requests
import time

BASE_URL = "http://localhost:8000"

# Reset environment
resp = requests.post(f"{BASE_URL}/reset")
obs = resp.json()
print("Environment reset!")

# Send actions
actions = [
    {"action_type": "key", "key": 39, "key_state": "down"},  # Right
    {"action_type": "key", "key": 40, "key_state": "down"},  # Down
    {"action_type": "key", "key": 13, "key_state": "down"},  # Enter
]

for action in actions:
    resp = requests.post(f"{BASE_URL}/step", json={"action": action})
    obs = resp.json()
    print(f"Action sent: {action}")
    time.sleep(0.2)
```

### Bash Script Example

```bash
#!/bin/bash
BASE_URL="http://localhost:8000"

# Reset
curl -X POST "$BASE_URL/reset" > /dev/null

# Move right
curl -X POST "$BASE_URL/step" \
  -H 'Content-Type: application/json' \
  -d '{"action": {"action_type": "key", "key": 39, "key_state": "down"}}'

sleep 0.2

# Move down
curl -X POST "$BASE_URL/step" \
  -H 'Content-Type: application/json' \
  -d '{"action": {"action_type": "key", "key": 40, "key_state": "down"}}'
```

## Advanced Usage

### Custom Screen Size

```bash
SCREEN_WIDTH=1280 SCREEN_HEIGHT=720 ./run_bomberman.sh
```

### Multiple Instances

Run multiple Bomberman instances on different ports:

```bash
# Instance 1 (ports 8000, 9090)
./run_bomberman.sh

# Instance 2 (modify script to use ports 8001, 9091)
# Edit run_bomberman.sh to change ports
```

### Integration with RL Frameworks

The environment can be integrated with RL frameworks like:
- Stable-Baselines3
- Ray RLlib
- OpenAI Gym

Example Gym wrapper:
```python
import gym
from gym import spaces
import requests
import base64
import numpy as np
from PIL import Image
import io

class BombermanEnv(gym.Env):
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.action_space = spaces.Discrete(5)  # 4 arrows + enter
        self.observation_space = spaces.Box(
            low=0, high=255, shape=(600, 800, 3), dtype=np.uint8
        )
        self.session = requests.Session()
        
    def reset(self):
        resp = self.session.post(f"{self.base_url}/reset")
        obs = resp.json()["observation"]
        screen = self._decode_screen(obs["screen"])
        return screen
    
    def step(self, action):
        key_map = [37, 38, 39, 40, 13]  # left, up, right, down, enter
        action_data = {
            "action_type": "key",
            "key": key_map[action],
            "key_state": "down"
        }
        resp = self.session.post(
            f"{self.base_url}/step",
            json={"action": action_data}
        )
        obs = resp.json()["observation"]
        screen = self._decode_screen(obs["screen"])
        return screen, 0, False, {}
    
    def _decode_screen(self, b64_str):
        img_data = base64.b64decode(b64_str)
        img = Image.open(io.BytesIO(img_data))
        return np.array(img)
```

## License

Bomberman game files are provided by GamesNostalgia.com. Please refer to their license terms.

Mednafen emulator: https://mednafen.github.io/

## Support

For issues related to:
- **OpenEnv**: Check the main `openenv/README.md`
- **Bomberman**: Check game logs and this guide
- **Mednafen**: Visit https://mednafen.github.io/

## Changelog

- **2024-12-09**: Initial Bomberman environment setup with PulseAudio support



