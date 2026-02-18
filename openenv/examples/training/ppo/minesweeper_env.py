import gymnasium as gym
from gymnasium import spaces
import numpy as np
import subprocess
import requests
import time
import os
try:
    from .openenv_gym import OpenEnvGym
except ImportError:
    from openenv_gym import OpenEnvGym

class MinesweeperEnv(OpenEnvGym):
    def __init__(self, container_name="openenv", **kwargs):
        # Action Space:
        # For simplicity, 9x9 Beginner = 81 cells.
        # But this is Expert mode (30x16)? Or default?
        # Let's assume generic click mapping.
        # Action: Discrete(Row * Col) -> Left Click
        # We start with 9x9 (81 actions) for manageable training?
        # Or Expert (480 actions).
        
        self.rows = 16
        self.cols = 30
        self.grid_x = 12
        self.grid_y = 55
        self.cell_size = 16
        
        # Discrete action for every cell (Left Click only for now)
        action_space = spaces.Discrete(self.rows * self.cols)
        
        super().__init__(action_space=action_space, **kwargs)
        
        self.container_name = container_name
        self.grid_address = None
        self.memory_space = spaces.Box(low=0, high=255, shape=(24, 32), dtype=np.uint8) # Approx grid size in memory
        
        # Update Observation Space
        self.observation_space = spaces.Dict({
            "screen": self.observation_space["screen"],
            "memory": self.memory_space
        })
        
        # Initialize Memory Address
        self._find_grid_address()

    def _find_grid_address(self):
        print("Locating Minesweeper Grid in Memory...")
        for attempt in range(15):
            try:
                # 1. Get PID
                res = requests.get(f"{self.api_url}/process/winemine.exe")
                if res.status_code != 200:
                    time.sleep(1)
                    continue
                    
                pid = res.json()["pid"]
                
                # 2. Run Scanner via API
                print("Requesting Grid Density Scan via API...")
                res = requests.post(f"{self.api_url}/memory/scan_density", json={"pid": pid})
                
                if res.status_code == 200:
                    data = res.json()
                    if data.get("found"):
                        self.grid_address = data["address"]
                        print(f"Grid Address Found: {hex(self.grid_address)}")
                        return
                    else:
                        print("Grid Address NOT FOUND by API (retrying...)")
                else:
                    print(f"API Scan Error: {res.status_code} {res.text}")
            except Exception as e:
                print(f"Error finding grid: {e}")
            
            time.sleep(1)
        print("Could not find winemine.exe process or grid after 15 attempts")

    def _read_memory(self):
        if not self.grid_address:
            return np.zeros((24, 32), dtype=np.uint8)
            
        try:
            # Read enough bytes for the grid
            # Expert is 30x16, but stride is 32 bytes (border included)
            # Total bytes ~ 32 * 24 ?
            size = 32 * 24 
            res = requests.post(f"{self.api_url}/memory/read", json={
                "pid": 12, # Hardcoded or cached? Should cache PID.
                "address": self.grid_address, 
                "size": size
            })
            if res.status_code == 200:
                data_hex = res.json()["data_hex"]
                data = bytes.fromhex(data_hex)
                # Reshape to 2D
                arr = np.frombuffer(data, dtype=np.uint8)
                # Pad or truncate to match observation space
                target_size = 32 * 24
                if len(arr) < target_size:
                    arr = np.pad(arr, (0, target_size - len(arr)))
                else:
                    arr = arr[:target_size]
                return arr.reshape((24, 32)) # Verify stride
        except:
            pass
        return np.zeros((24, 32), dtype=np.uint8)

    def step(self, action):
        # Map Action -> Click
        # 480 actions -> (row, col)
        r = action // self.cols
        c = action % self.cols
        
        # Pixel calculation
        px = self.grid_x + (c * self.cell_size) + (self.cell_size // 2)
        py = self.grid_y + (r * self.cell_size) + (self.cell_size // 2)
        
        # Send API Step
        payload = {
            "action_type": "mouse",
            "x": int(px),
            "y": int(py),
            "button": "left",
            "mouse_state": "click"
        }
        
        obs_dict, _, _, _, _ = self.step_api(payload)
        
        # Add Memory
        if obs_dict:
            mem_obs = self._read_memory()
            obs_dict["memory"] = mem_obs
            
            # TODO: Calculate Reward from Memory change
            # e.g. If memory shows 'Boom' (0x8F, 0xCC?) -> Done, Reward -10
            # If revealed count increases -> Reward +1
            reward = 0
            done = False
            
            # Check for Boom in memory (0xCC is mine, 0x8A is mine exploded... need values)
            # For now, simplistic check:
            if np.any(mem_obs == 0xCC) or np.any(mem_obs == 0x8A): # Example mine values
                 done = True
                 reward = -10
            
            return obs_dict, reward, done, False, {}
        else:
            return {}, 0, True, False, {}
            
    def reset(self, seed=None, options=None):
        obs, info = super().reset(seed=seed, options=options)
        
        # Game has been restarted by super().reset(), so we must find the new PID/Address
        self._find_grid_address()
        
        if obs:
             obs["memory"] = self._read_memory()
        return obs, info
