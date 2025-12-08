# OpenEnv Architecture

## Overview

OpenEnv provides a standardized HTTP interface for reinforcement learning environments. This implementation enables RL agents to interact with Windows applications running in Wine through Docker containerization.

## System Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            RL TRAINING HOST                                │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         RL Training Loop                             │  │
│  │                                                                      │  │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │  │
│  │   │   Policy    │───▶│    Agent    │───▶│   Experience Buffer    │ │  │
│  │   │   Network   │    │   act(obs)  │    │   (obs, action, reward) │ │  │
│  │   └─────────────┘    └──────┬──────┘    └─────────────────────────┘ │  │
│  │                             │ action                                 │  │
│  └─────────────────────────────┼────────────────────────────────────────┘  │
│                                │                                           │
│                                ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      OpenEnv HTTP Client                             │  │
│  │                                                                      │  │
│  │   env.reset() ────▶ POST /reset ────▶ observation                   │  │
│  │   env.step(a) ────▶ POST /step  ────▶ observation, reward, done     │  │
│  │   env.state   ────▶ GET /state  ────▶ environment metadata          │  │
│  │                                                                      │  │
│  └───────────────────────────────┬──────────────────────────────────────┘  │
│                                  │ HTTP (port 8000)                        │
└──────────────────────────────────┼─────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          DOCKER CONTAINER                                    │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                         supervisord                                    │  │
│  │                    (Process Management)                                │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│           │              │              │              │                     │
│           ▼              ▼              ▼              ▼                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │    Xvfb    │ │  FastAPI    │ │ syncinput   │ │  wineapp    │            │
│  │  Display   │ │  Server     │ │   .exe      │ │ (notepad)   │            │
│  │   :99      │ │  :8000      │ │  TCP:9090   │ │             │            │
│  └─────────────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘            │
│         │               │               │               │                    │
│         │               │    Input      │    Windows    │                    │
│         │               │    Commands   │    API        │                    │
│         │               │  ◀────────────│──────────────▶│                    │
│         │               │               │               │                    │
│         │      Screen   │               │               │                    │
│         │      Capture  │               │               │                    │
│         │  ◀────────────│───────────────│───────────────│                    │
│         │    (FFmpeg)   │               │               │                    │
│         │               │               │               │                    │
│  ┌──────▼───────────────▼───────────────▼───────────────▼──────┐            │
│  │                    X11 Display :99                          │            │
│  │              (Virtual Framebuffer 800x600)                  │            │
│  └─────────────────────────────────────────────────────────────┘            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. FastAPI Server (`src/server/app.py`)

HTTP server exposing OpenEnv-compatible API:

```python
@app.post("/reset")
async def reset():
    """Reset environment, return initial observation"""
    observation = env.reset()
    return serialize_observation(observation)

@app.post("/step")
async def step(action):
    """Execute action, return new observation"""
    observation = env.step(action)
    return serialize_observation(observation)
```

**Responsibilities:**
- Accept HTTP requests from RL client
- Serialize observations (screen → base64 JPEG)
- Manage TCP connection to syncinput.exe
- Capture screen via FFmpeg

### 2. Wine Environment (`src/server/wine_environment.py`)

Core environment logic:

```python
class WineEnvironment:
    def reset(self) -> WineObservation:
        """Reset to initial state, capture screen"""
        self._accept_input_connection()
        return WineObservation(screen=self._capture_screen())
    
    def step(self, action: WineAction) -> WineObservation:
        """Execute action, capture resulting screen"""
        self._send_input(action)
        return WineObservation(screen=self._capture_screen())
```

**Responsibilities:**
- Accept syncinput.exe TCP connections
- Send keyboard/mouse commands
- Capture screen using FFmpeg
- Handle reconnection on timeout

### 3. syncinput.exe (`src/syncinput.cpp`)

Windows executable running under Wine:

```
┌─────────────────────────────────────────────────┐
│                 syncinput.exe                   │
│                                                 │
│  ┌───────────┐    ┌───────────┐    ┌─────────┐ │
│  │   TCP     │───▶│  Parse    │───▶│ Windows │ │
│  │  Client   │    │  Commands │    │   API   │ │
│  │  :9090    │    │  K65,1|   │    │SendInput│ │
│  └───────────┘    └───────────┘    └─────────┘ │
│                                                 │
│  ┌───────────────────────────────────────────┐ │
│  │  Window Finder Thread                     │ │
│  │  - Find window by process name            │ │
│  │  - Update HWND every 2 seconds            │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  ┌───────────────────────────────────────────┐ │
│  │  Health Check Thread                      │ │
│  │  - Exit if no ping for 10 seconds         │ │
│  │  - Allows supervisor to restart           │ │
│  └───────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**Protocol:**
- `K{keycode},{state}|` - Keyboard (state: 1=down, 0=up)
- `M{left},{state},{x},{y},{w},{h}|` - Mouse
- `\x00` - Ping (keep-alive)

### 4. Xvfb (Virtual Display)

Virtual framebuffer providing X11 display without physical hardware:

```bash
Xvfb :99 -screen 0 800x600x16
```

All Wine applications render to this virtual display, which FFmpeg captures.

## Data Flow

### Step Execution Flow

```
1. RL Agent calls env.step({"action_type": "key", "key": 65})
                    │
                    ▼
2. HTTP Client sends POST /step to FastAPI server
                    │
                    ▼
3. WineEnvironment._send_input() sends "K65,1|K65,0|" to syncinput.exe
                    │
                    ▼
4. syncinput.exe calls Windows SendInput() API
                    │
                    ▼
5. Wine processes input, updates Notepad window
                    │
                    ▼
6. WineEnvironment._capture_screen() calls FFmpeg
                    │
                    ▼
7. FFmpeg captures X11 display :99 → JPEG
                    │
                    ▼
8. Server encodes JPEG → base64, returns to client
                    │
                    ▼
9. RL Agent receives observation (800x600x3 numpy array)
```

### Observation Format

```json
{
  "observation": {
    "screen": "/9j/4AAQSkZJRg...",  // Base64 JPEG
    "screen_shape": [600, 800, 3],   // [H, W, C]
    "metadata": {}
  },
  "reward": null,    // Application-specific (not implemented)
  "done": false      // Episode termination (not implemented)
}
```

## RL Integration

### Training Loop

```python
import numpy as np
from stable_baselines3 import PPO
from gymnasium import Env, spaces

class NotepadEnv(Env):
    """Gymnasium wrapper for OpenEnv Wine environment"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.client = OpenEnvClient(base_url)
        
        # Observation: 800x600 RGB image
        self.observation_space = spaces.Box(
            low=0, high=255, 
            shape=(600, 800, 3), 
            dtype=np.uint8
        )
        
        # Action: discrete keyboard keys
        self.action_space = spaces.Discrete(128)
    
    def reset(self, seed=None):
        obs = self.client.reset()
        return obs, {}
    
    def step(self, action):
        obs = self.client.step({
            "action_type": "key",
            "key": int(action),
            "key_state": "down"
        })
        
        # Compute reward (application-specific)
        reward = self._compute_reward(obs)
        done = False
        
        return obs, reward, done, False, {}
    
    def _compute_reward(self, obs):
        # Example: OCR to check typed text matches target
        # Or: pixel-based reward for specific UI states
        return 0.0

# Train with PPO
env = NotepadEnv()
model = PPO("CnnPolicy", env, verbose=1)
model.learn(total_timesteps=100000)
```

### Multiplexing for Parallel Training

```
┌─────────────────────────────────────────────────────────────────┐
│                    RL Training Orchestrator                     │
│                                                                 │
│   ┌─────────────┐  ┌─────────────┐       ┌─────────────┐       │
│   │   Worker 1  │  │   Worker 2  │  ...  │   Worker N  │       │
│   └──────┬──────┘  └──────┬──────┘       └──────┬──────┘       │
└──────────┼────────────────┼─────────────────────┼───────────────┘
           │                │                     │
           ▼                ▼                     ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Docker Container │ │ Docker Container │ │ Docker Container │
│   :8000, :9090   │ │   :8001, :9091   │ │   :800N, :909N   │
│                  │ │                  │ │                  │
│  ┌────────────┐  │ │  ┌────────────┐  │ │  ┌────────────┐  │
│  │  Notepad   │  │ │  │  Notepad   │  │ │  │  Notepad   │  │
│  │ Instance 1 │  │ │  │ Instance 2 │  │ │  │ Instance N │  │
│  └────────────┘  │ │  └────────────┘  │ │  └────────────┘  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

**Scaling:**
```bash
# Start multiple environments
for i in {0..7}; do
  docker run -d --name openenv-$i \
    -p $((8000+i)):8000 \
    -p $((9090+i)):9090 \
    -e APP_FILE=notepad \
    openenv
done

# Train with SubprocVecEnv
from stable_baselines3.common.vec_env import SubprocVecEnv

def make_env(port):
    def _init():
        return NotepadEnv(f"http://localhost:{port}")
    return _init

envs = SubprocVecEnv([make_env(8000+i) for i in range(8)])
model = PPO("CnnPolicy", envs, n_steps=128)
```

## Performance Considerations

### Latency Breakdown

| Operation | Time |
|-----------|------|
| HTTP request/response | ~5ms |
| Send input via TCP | ~1ms |
| Wine process input | ~10ms |
| FFmpeg screen capture | ~50ms |
| JPEG encode + base64 | ~10ms |
| **Total step latency** | **~80ms** |

### Optimization Strategies

1. **Reduce capture frequency**: Skip frames for actions that don't need observation
2. **Lower resolution**: Use 400x300 for faster capture
3. **Batch actions**: Send multiple keys in one request
4. **Async capture**: Overlap capture with network I/O

## Extension Points

### Custom Applications

Replace Notepad with any Windows application:

```bash
docker run -d --name openenv \
  -e APP_FILE=/apps/myapp.exe \
  -e WINDOW_TITLE="My Application" \
  -v /path/to/apps:/apps \
  openenv
```

### Custom Reward Functions

Implement in `wine_environment.py`:

```python
def compute_reward(self, obs: WineObservation) -> float:
    """
    Application-specific reward computation
    
    Options:
    - OCR text recognition
    - Template matching for UI elements
    - Pixel difference from target state
    - External oracle/LLM evaluation
    """
    return 0.0
```

### Custom Actions

Extend `WineAction` model:

```python
@dataclass
class WineAction:
    action_type: str  # "key", "mouse", "text", "combo"
    
    # For action_type="text"
    text: Optional[str] = None
    
    # For action_type="combo"
    keys: Optional[List[int]] = None
```

## Security Considerations

- Container runs as root (Wine requirement)
- No network isolation within container
- Input injection could affect any window in Wine session
- Consider read-only file systems for production

## Future Work

1. **GPU acceleration** for screen capture
2. **Audio observation** support
3. **Multi-window** management
4. **Save/load** environment state
5. **Reward shaping** framework
6. **Curriculum learning** support

