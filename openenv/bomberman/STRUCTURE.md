# Bomberman Package Structure

This document describes the organization of Bomberman-related files.

## Directory Structure

```
openenv/bomberman/
├── README.md                    # Complete documentation
├── QUICKSTART.md                # Quick start guide
├── STRUCTURE.md                 # This file
├── run_bomberman.sh            # Main launcher script
├── random_bomberman_agent.py   # Example random agent
├── requirements.txt            # Python dependencies
└── .gitignore                  # Git ignore rules

openenv/games/Bomberman/         # Game files (referenced by container)
├── med/
│   ├── mednafen.exe           # PC Engine emulator
│   ├── game.pce               # Bomberman ROM
│   └── ...                    # Other emulator files
├── Bomberman.bat               # Original launcher
└── README.txt                  # Game instructions
```

## File Descriptions

### Documentation

- **README.md**: Comprehensive guide covering:
  - Installation and setup
  - API usage
  - Troubleshooting
  - Examples
  - Advanced usage

- **QUICKSTART.md**: Minimal guide to get started quickly

- **STRUCTURE.md**: This file - explains package organization

### Scripts

- **run_bomberman.sh**: 
  - Builds Docker image
  - Starts Bomberman container
  - Configures environment variables
  - Mounts game files
  - Exposes API ports

- **random_bomberman_agent.py**:
  - Demonstrates API usage
  - Sends random actions
  - Useful for testing

### Configuration

- **requirements.txt**: Python dependencies for the agent
- **.gitignore**: Git ignore patterns

## Dependencies

### System Requirements
- Docker
- Python 3.6+
- Bash shell

### Python Dependencies
- `requests` (for API client)

Install with:
```bash
pip install -r requirements.txt
```

## Integration Points

The Bomberman package integrates with:

1. **OpenEnv Core** (`openenv/`):
   - Uses shared Dockerfile
   - Uses shared supervisor config
   - Uses shared scripts

2. **Game Files** (`openenv/games/Bomberman/`):
   - Mounted into container at `/games/Bomberman`
   - Contains emulator and ROM

3. **API Server** (`openenv/src/server/`):
   - Provides HTTP endpoints
   - Handles screen capture
   - Manages input injection

## Usage Flow

1. User runs `run_bomberman.sh`
2. Script builds Docker image (if needed)
3. Container starts with Bomberman configured
4. API becomes available at `http://localhost:8000`
5. User can:
   - View game via browser
   - Send actions via API
   - Use random agent for testing

## Ports

- **8000**: HTTP API (reset, step, state, viewer, stream)
- **9090**: Input socket (internal, for syncinput.exe)

## Environment Variables

Set via `run_bomberman.sh`:
- `SCREEN_WIDTH`: Display width (default: 800)
- `SCREEN_HEIGHT`: Display height (default: 600)
- `APP_FILE`: Path to executable (`/games/Bomberman/med/mednafen.exe`)
- `APP_ARGS`: Command line arguments (`-video.fs 0 /games/Bomberman/med/game.pce`)
- `WINDOW_TITLE`: Window title for input injection (`game` - matches the actual window title `[game]`)

## Notes

- Game files are not included in this package (see `openenv/games/`)
- The package assumes OpenEnv core is properly set up
- Audio support requires PulseAudio (configured in Docker image)
- Screen capture uses FFmpeg via X11grab



