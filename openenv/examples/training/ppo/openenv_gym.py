import gymnasium as gym
import numpy as np
import requests
import base64
import time
from gymnasium import spaces

try:
    import cv2
except ImportError:
    cv2 = None

class OpenEnvGym(gym.Env):
    """
    Generic Gymnasium wrapper for OpenEnv.
    Handles:
    - Connecting to API
    - Action conversion (Discrete/MultiDiscrete -> Mouse/Key)
    - Observation (Screen screenshot -> CNN-ready array)
    """
    def __init__(self, api_url="http://localhost:8000", 
                 screen_width=800, screen_height=600,
                 action_space=None, # User must define
                 reset_callback=None # Function to call on reset (e.g. click smiley)
                 ):
        super().__init__()
        self.api_url = api_url
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # Default Action Space: Simple mouse click grid? No, too specific.
        # We require the subclass to define action_space and process_action.
        self.action_space = action_space if action_space else spaces.Discrete(1)
        
        # Observation Space: Dict with 'screen'
        # Screen is (H, W, 3) RGB
        self.observation_space = spaces.Dict({
            "screen": spaces.Box(low=0, high=255, shape=(screen_height, screen_width, 3), dtype=np.uint8)
        })
        
        self.reset_callback = reset_callback

    def _get_obs(self):
        return np.zeros((self.screen_height, self.screen_width, 3), dtype=np.uint8)
    
    def step_api(self, action_payload):
        """
        Send raw action payload to OpenEnv
        """
        try:
            # Wrap payload in 'action' key to match API expectation
            final_payload = {"action": action_payload}
            res = requests.post(f"{self.api_url}/step", json=final_payload)
            if res.status_code == 200:
                data = res.json()
                # Server might return 'screen' or 'screen_image'
                obs_data = data.get("observation", {})
                b64 = obs_data.get("screen") or obs_data.get("screen_image")
                
                if b64 and b64.startswith("data:image"):
                    b64 = b64.split(",")[1]
                
                # Decode
                if cv2 and b64:
                    img_data = base64.b64decode(b64)
                    np_arr = np.frombuffer(img_data, np.uint8)
                    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    
                    # Ensure correct shape
                    if img.shape[:2] != (self.screen_height, self.screen_width):
                        img = cv2.resize(img, (self.screen_width, self.screen_height))
                else:
                    # Fallback if no CV2
                    img = np.zeros((self.screen_height, self.screen_width, 3), dtype=np.uint8)
                
                obs = {"screen": img}
                
                # Basic Reward/Done (Subclass should override)
                reward = 0
                done = False
                truncated = False
                info = {}
                
                return obs, reward, done, truncated, info
            else:
                print(f"API Step Error: Status {res.status_code} - {res.text}")
                # Return dummy obs to prevent crash
                dummy_obs = {"screen": self._get_obs(), "memory": np.zeros((24, 32), dtype=np.uint8)}
                return dummy_obs, 0, True, False, {}
        except Exception as e:
            print(f"API Step Error: {e}")
            if 'data' in locals():
                print(f"Received Data: {data}")
            # Return dummy obs to prevent crash
            dummy_obs = {"screen": self._get_obs(), "memory": np.zeros((24, 32), dtype=np.uint8)}
            return dummy_obs, 0, True, False, {}

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        
        # 1. OpenEnv Reset
        requests.post(f"{self.api_url}/reset")
        time.sleep(2) # Wait for app reload
        
        if self.reset_callback:
            self.reset_callback(self)
            
        # Get initial obs via a dummy step
        obs, _, _, _, _ = self.step_api({"action_type": "mouse", "mouse_state": "move", "x": 0, "y": 0})
        return obs, {}

    def step(self, action):
        raise NotImplementedError("Subclasses must implement step() to map action -> API payload and calculate reward")
