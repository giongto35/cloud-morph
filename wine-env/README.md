# Wine Environment

Docker-based Wine environment with HTTP API for running and controlling Windows applications.

## Quick Start

```bash
# Build and run
./run.sh

# Or with custom app
./run.sh /apps/myapp.exe "My App Window"
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/reset` | POST | Reset environment, get screenshot |
| `/step` | POST | Execute action, get screenshot |
| `/state` | GET | Get current state |
| `/stream` | GET | MJPEG live stream |
| `/viewer` | GET | HTML viewer page |

### Examples

```bash
# Health check
curl http://localhost:8000/health

# Reset and capture screen
curl -X POST http://localhost:8000/reset | jq '.observation.screen' | head -c 100

# Send keystroke (A = 65)
curl -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "key", "key": 65, "key_state": "down"}'

# Mouse click at center
curl -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "mouse", "button": "left", "mouse_state": "down", "x": 0.5, "y": 0.5}'
```

### Key Codes

- A-Z: 65-90
- 0-9: 48-57
- Enter: 13
- Space: 32
- Backspace: 8
- Arrow keys: 37 (←), 38 (↑), 39 (→), 40 (↓)

## Manual Commands

```bash
# Build image
docker build -t wine-env .

# Run container
docker run -d --name wine-env \
  -p 8000:8000 -p 9090:9090 \
  -e SCREEN_WIDTH=800 \
  -e SCREEN_HEIGHT=600 \
  -e APP_FILE=notepad \
  -e WINDOW_TITLE="Notepad" \
  wine-env

# Check status
docker exec wine-env supervisorctl -s http://127.0.0.1:9001 status

# View logs
docker exec wine-env cat /app/logs/wineapp.log
docker exec wine-env cat /app/logs/syncinput.log

# Stop
docker stop wine-env && docker rm wine-env
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCREEN_WIDTH` | 800 | Virtual screen width |
| `SCREEN_HEIGHT` | 600 | Virtual screen height |
| `APP_FILE` | notepad | Wine application to run |
| `WINDOW_TITLE` | Notepad | Window title for input targeting |

## Structure

```
wine-env/
├── Dockerfile
├── run.sh              # Quick start script
├── config/
│   └── supervisord.conf
├── scripts/
│   └── download_gecko_and_mono.sh
└── src/
    ├── syncinput.cpp   # Input injection (compiled to .exe)
    ├── models.py       # Data models
    └── server/
        ├── app.py      # FastAPI server
        └── wine_environment.py
```

## Troubleshooting

**wineapp FATAL**: Check `/app/logs/wineapp.log` - usually missing DISPLAY or app not found.

**syncinput not connecting**: Check `/app/logs/syncinput.log` - should see "Connected!" and "Found window".

**Black screen**: Xvfb may not be running. Check `supervisorctl status`.

**Input not working**: syncinput needs to find the window. Verify `WINDOW_TITLE` matches actual title.

