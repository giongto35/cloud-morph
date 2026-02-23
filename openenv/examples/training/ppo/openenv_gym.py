"""Gymnasium wrapper for OpenEnv HTTP API.

Exposes StarCraft (or any OpenEnv app) as a standard Gymnasium environment
with 84x84x3 RGB observations and Discrete(35) actions.
"""

import base64
import io
import time

import cv2
import gymnasium as gym
import numpy as np
import requests


# 10 keyboard actions
KEY_ACTIONS = [
    {"action_type": "key", "key": "s"},       # 0: select / single player
    {"action_type": "key", "key": "b"},       # 1: build
    {"action_type": "key", "key": "m"},       # 2: move
    {"action_type": "key", "key": "p"},       # 3: patrol
    {"action_type": "key", "key": "a"},       # 4: attack
    {"action_type": "key", "key": "h"},       # 5: hold
    {"action_type": "key", "key": "Return"},  # 6: confirm / enter
    {"action_type": "key", "key": "Escape"},  # 7: cancel / escape
    {"action_type": "key", "key": "F1"},      # 8: select all army
    {"action_type": "key", "key": "F2"},      # 9: new game / hotkey
]

# 25 mouse click actions on a 5x5 grid over 640x480 screen
MOUSE_ACTIONS = []
for row in range(5):
    for col in range(5):
        x = int(64 + col * (512 / 4))  # 64, 192, 320, 448, 576
        y = int(48 + row * (384 / 4))  # 48, 144, 240, 336, 432
        MOUSE_ACTIONS.append({
            "action_type": "mouse",
            "x": x, "y": y,
            "button": "left",
            "mouse_state": "click",
        })

ALL_ACTIONS = KEY_ACTIONS + MOUSE_ACTIONS  # 35 total


class OpenEnvGym(gym.Env):
    """Gymnasium environment wrapping OpenEnv HTTP API."""

    metadata = {"render_modes": ["rgb_array"]}

    def __init__(self, url="http://localhost:8000", obs_size=84):
        super().__init__()
        self.url = url.rstrip("/")
        self.obs_size = obs_size
        self.observation_space = gym.spaces.Box(
            low=0, high=255,
            shape=(obs_size, obs_size, 3),
            dtype=np.uint8,
        )
        self.action_space = gym.spaces.Discrete(len(ALL_ACTIONS))
        self._last_raw_obs = None

    def _decode_screen(self, screen_b64: str) -> np.ndarray:
        """Decode base64 JPEG to 84x84 RGB numpy array."""
        jpg_bytes = base64.b64decode(screen_b64)
        arr = cv2.imdecode(
            np.frombuffer(jpg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if arr is None:
            return np.zeros((self.obs_size, self.obs_size, 3), dtype=np.uint8)
        # BGR -> RGB
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        # Resize to 84x84
        arr = cv2.resize(arr, (self.obs_size, self.obs_size), interpolation=cv2.INTER_AREA)
        return arr

    def _post(self, endpoint: str, json=None, retries=3) -> dict:
        for attempt in range(retries):
            try:
                r = requests.post(f"{self.url}{endpoint}", json=json or {}, timeout=10)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == retries - 1:
                    raise
                time.sleep(1)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        resp = self._post("/reset")
        obs = self._decode_screen(resp["observation"]["screen"])
        self._last_raw_obs = obs
        return obs, {}

    def step(self, action: int):
        action_dict = ALL_ACTIONS[action]
        resp = self._post("/step", json=action_dict)

        obs = self._decode_screen(resp["observation"]["screen"])
        self._last_raw_obs = obs
        reward = resp.get("reward") or 0.0
        done = resp.get("done", False)

        return obs, float(reward), done, False, {}

    def render(self):
        return self._last_raw_obs

    def close(self):
        pass
