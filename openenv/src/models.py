"""Data models for Wine Environment"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import numpy as np


@dataclass
class WineAction:
    """Action for Wine environment"""
    action_type: str  # "key" or "mouse"
    key: Optional[int] = None  # Virtual key code
    key_state: Optional[str] = None  # "down" or "up"
    x: Optional[float] = None  # X coordinate (0-1 normalized or pixels)
    y: Optional[float] = None  # Y coordinate (0-1 normalized or pixels)
    button: Optional[str] = None  # "left" or "right"
    mouse_state: Optional[str] = None  # "down", "up", or "move"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WineObservation:
    """Observation containing screen frame"""
    screen: np.ndarray  # Screen capture (BGR format)
    screen_shape: tuple = field(init=False)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.screen, np.ndarray):
            self.screen_shape = self.screen.shape
        elif isinstance(self.screen, list):
            self.screen = np.array(self.screen, dtype=np.uint8)
            self.screen_shape = self.screen.shape


@dataclass
class WineState:
    """Environment state"""
    episode_id: int
    step_count: int
    app_path: str
    app_file: str
    window_title: str
    screen_width: int
    screen_height: int

