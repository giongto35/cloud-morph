"""Wine Environment implementation"""

from typing import Optional
import numpy as np
import os
import socket
import time
import subprocess
import tempfile
import cv2

from models import WineAction, WineObservation, WineState


class WineEnvironment:
    """Wine Environment with screen capture and input injection"""
    
    def __init__(
        self,
        screen_width: int = 800,
        screen_height: int = 600,
    ):
        self.app_file = os.getenv("APP_FILE", "notepad")
        self.window_title = os.getenv("WINDOW_TITLE", "Notepad")
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        self.input_socket: Optional[socket.socket] = None
        self.input_conn: Optional[socket.socket] = None
        self._init_input_listener()
        
        self._episode_id = 0
        self._step_count = 0
    
    def _init_input_listener(self):
        """Start TCP listener for syncinput.exe"""
        try:
            self.input_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.input_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.input_socket.bind(('0.0.0.0', 9090))
            self.input_socket.listen(1)
            self.input_socket.settimeout(1.0)
            print("✓ Input listener on port 9090")
        except Exception as e:
            print(f"Warning: Input listener failed: {e}")
            self.input_socket = None
    
    def _accept_input_connection(self):
        """Accept syncinput.exe connection"""
        if not self.input_socket:
            return False
        try:
            conn, addr = self.input_socket.accept()
            self.input_conn = conn
            conn.settimeout(5.0)
            print(f"✓ syncinput connected from {addr}")
            return True
        except socket.timeout:
            return False
        except Exception as e:
            print(f"Accept error: {e}")
            return False
    
    def _send_input(self, message: bytes):
        """Send input to syncinput.exe"""
        if not self.input_conn:
            self._accept_input_connection()
        
        if self.input_conn:
            try:
                self.input_conn.sendall(message)
                self.input_conn.sendall(b'\x00')  # Ping
            except Exception as e:
                print(f"Send error: {e}")
                self.input_conn = None
                self._accept_input_connection()
    
    def reset(self) -> WineObservation:
        """Reset environment"""
        self._episode_id += 1
        self._step_count = 0
        self._accept_input_connection()
        return WineObservation(screen=self._capture_screen())
    
    def step(self, action: WineAction) -> WineObservation:
        """Execute action"""
        if action.action_type == "key":
            key_code = action.key or 0
            key_state = action.key_state or "down"
            
            # For A-Z keys, send both down and up
            if key_state == "down" and 65 <= key_code <= 90:
                self._send_input(f"K{key_code},1|".encode())
                time.sleep(0.05)
                self._send_input(f"K{key_code},0|".encode())
            else:
                state = 1 if key_state == "down" else 0
                self._send_input(f"K{key_code},{state}|".encode())
                
        elif action.action_type == "mouse":
            is_left = 1 if (action.button or "left") == "left" else 0
            state = 1 if (action.mouse_state or "down") == "down" else (2 if action.mouse_state == "up" else 0)
            x, y = action.x or 0.5, action.y or 0.5
            
            # Normalize coordinates
            if x <= 1.0 and y <= 1.0:
                x, y = x * self.screen_width, y * self.screen_height
            
            self._send_input(f"M{is_left},{state},{x},{y},{self.screen_width},{self.screen_height}|".encode())
        
        self._step_count += 1
        time.sleep(0.2)
        return WineObservation(screen=self._capture_screen())
    
    def _capture_screen(self) -> np.ndarray:
        """Capture screen using FFmpeg"""
        display = os.getenv("DISPLAY", ":99")
        
        try:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_path = tmp.name
            
            subprocess.run([
                'ffmpeg', '-f', 'x11grab', '-draw_mouse', '0',
                '-video_size', f'{self.screen_width}x{self.screen_height}',
                '-i', f'{display}+0,0',
                '-vf', f'scale={self.screen_width}:{self.screen_height}',
                '-frames:v', '1', '-q:v', '2', '-y', tmp_path
            ], capture_output=True, timeout=2.0, check=True)
            
            frame = cv2.imread(tmp_path)
            os.unlink(tmp_path)
            
            if frame is not None:
                return frame
        except Exception as e:
            print(f"Capture error: {e}")
        
        return np.zeros((self.screen_height, self.screen_width, 3), dtype=np.uint8)
    
    @property
    def state(self) -> WineState:
        """Get current state"""
        return WineState(
            episode_id=self._episode_id,
            step_count=self._step_count,
            app_path="/app",
            app_file=self.app_file,
            window_title=self.window_title,
            screen_width=self.screen_width,
            screen_height=self.screen_height,
        )
    
    def close(self):
        """Cleanup"""
        if self.input_conn:
            try: self.input_conn.close()
            except: pass
        if self.input_socket:
            try: self.input_socket.close()
            except: pass

