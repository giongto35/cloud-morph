"""Memory-based reward wrapper for StarCraft mineral tracking.

Uses OpenEnv's /process/{name} and /memory/scan + /memory/read endpoints
to read the in-game mineral count and derive a reward signal.
"""

import struct
import time

import gymnasium as gym
import requests


class MemoryRewardWrapper(gym.Wrapper):
    """Wraps an OpenEnvGym to provide mineral-delta reward from game memory.

    Reward = delta_minerals * 0.01 - 0.001 (time penalty per step).
    Gracefully degrades to zero reward if memory scanning fails.
    """

    def __init__(self, env, process_name="StarCraft.exe", scan_delay=20):
        super().__init__(env)
        self.process_name = process_name
        self.scan_delay = scan_delay  # steps before first scan attempt
        self._url = env.url
        self._pid = None
        self._mineral_addr = None
        self._last_minerals = None
        self._step_count = 0
        self._scan_attempted = False

    def _get_pid(self):
        try:
            r = requests.get(f"{self._url}/process/{self.process_name}", timeout=5)
            if r.status_code == 200:
                self._pid = r.json()["pid"]
                return True
        except Exception:
            pass
        return False

    def _scan_minerals(self, target_value=50):
        """Scan for the mineral count address. Default StarCraft starting minerals = 50."""
        if self._pid is None:
            return False
        try:
            r = requests.post(
                f"{self._url}/memory/scan",
                json={"pid": self._pid, "value": target_value, "value_type": "int"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("count", 0) > 0:
                    # Use first candidate address
                    self._mineral_addr = data["addresses"][0]
                    return True
        except Exception:
            pass
        return False

    def _read_minerals(self) -> int | None:
        if self._pid is None or self._mineral_addr is None:
            return None
        try:
            r = requests.post(
                f"{self._url}/memory/read",
                json={"pid": self._pid, "address": self._mineral_addr, "size": 4},
                timeout=5,
            )
            if r.status_code == 200:
                import base64
                data_b64 = r.json()["data_b64"]
                raw = base64.b64decode(data_b64)
                return struct.unpack("<i", raw)[0]
        except Exception:
            pass
        return None

    def reset(self, **kwargs):
        obs, info = self.env.reset(**kwargs)
        self._step_count = 0
        self._last_minerals = None
        self._mineral_addr = None
        self._pid = None
        self._scan_attempted = False
        return obs, info

    def step(self, action):
        obs, _reward, terminated, truncated, info = self.env.step(action)
        self._step_count += 1

        reward = -0.001  # time penalty

        # Lazy initialization: try to find mineral address after delay
        if not self._scan_attempted and self._step_count >= self.scan_delay:
            self._scan_attempted = True
            if self._get_pid():
                self._scan_minerals()

        # Read minerals and compute delta reward
        minerals = self._read_minerals()
        if minerals is not None:
            if self._last_minerals is not None:
                delta = minerals - self._last_minerals
                reward += delta * 0.01
            self._last_minerals = minerals

        info["minerals"] = minerals
        info["mineral_addr"] = self._mineral_addr
        return obs, reward, terminated, truncated, info
