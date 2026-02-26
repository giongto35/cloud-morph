"""Wine Environment implementation"""

from typing import Optional
import numpy as np
import os
import socket
import time
import subprocess
import cv2
import mss
import re
import struct

from models import WineAction, WineObservation, WineState

# Key name mapping: normalizes various string key names to xdotool key names.
# Key name mapping: normalizes various string key names to xdotool key names.
_KEY_NAME_MAP = {
    'escape': 'Escape', 'return': 'Return', 'enter': 'Return',
    'tab': 'Tab', 'backspace': 'BackSpace', 'delete': 'Delete',
    'space': 'space', 'up': 'Up', 'down': 'Down', 'left': 'Left',
    'right': 'Right', 'shift': 'Shift_L', 'ctrl': 'Control_L',
    'alt': 'Alt_L', 'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4',
    'f5': 'F5', 'f6': 'F6', 'f7': 'F7', 'f8': 'F8', 'f9': 'F9',
    'f10': 'F10', 'f11': 'F11', 'f12': 'F12',
}

# Mapping from integer key codes to xdotool key names
_KEY_CODE_MAP = {
    8: 'BackSpace', 9: 'Tab', 13: 'Return', 27: 'Escape',
    32: 'space', 37: 'Left', 38: 'Up', 39: 'Right', 40: 'Down',
    46: 'Delete', 112: 'F1', 113: 'F2', 114: 'F3', 115: 'F4',
    116: 'F5', 117: 'F6', 118: 'F7', 119: 'F8', 120: 'F9',
    121: 'F10', 122: 'F11', 123: 'F12', 16: 'Shift_L', 17: 'Control_L',
    18: 'Alt_L',
}


def _resolve_key(key_value) -> Optional[str]:
    """Resolve a key value (int code or string name) to an xdotool key name."""
    if isinstance(key_value, str):
        return _KEY_NAME_MAP.get(key_value.lower(), key_value)
    elif isinstance(key_value, int):
        if key_value in _KEY_CODE_MAP:
            return _KEY_CODE_MAP[key_value]
        elif 32 <= key_value <= 126:
            return chr(key_value)
    return None


class WineEnvironment:
    """Wine Environment with screen capture and input injection.
    
    Supports two input methods (set via INPUT_METHOD env var):
      - "xdotool" (default): Uses xdotool for X11 input. Most reliable
        generic solution for any application running on the virtual display.
      - "socket": Uses syncinput.exe TCP connection for Windows-level input.
    """
    
    def __init__(
        self,
        screen_width: int = 800,
        screen_height: int = 600,
    ):
        self.app_file = os.getenv("APP_FILE", "notepad")
        self.window_title = os.getenv("WINDOW_TITLE", "Notepad")
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        self.input_method = os.getenv("INPUT_METHOD", "xdotool")
        self._display = os.getenv("DISPLAY", ":99")
        print(f"Input method: {self.input_method}")
        
        self.input_socket: Optional[socket.socket] = None
        self.input_conn: Optional[socket.socket] = None
        if self.input_method == "socket":
            self._init_input_listener()
        
        self._episode_id = 0
        self._step_count = 0
    
    # ── Socket input (syncinput.exe) ─────────────────────────────────

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
            try:
                conn.sendall(b'\x00')
            except:
                pass
            return True
        except socket.timeout:
            return False
        except Exception as e:
            print(f"Accept error: {e}")
            return False
    
    def _send_input(self, message: bytes):
        """Send input to syncinput.exe with retry on failure"""
        for attempt in range(3):
            if not self.input_conn:
                for _ in range(5):
                    if self._accept_input_connection():
                        break
                    time.sleep(1)
            
            if self.input_conn:
                try:
                    self.input_conn.sendall(message)
                    self.input_conn.sendall(b'\x00')
                    return
                except Exception as e:
                    print(f"Send error (attempt {attempt + 1}): {e}")
                    self.input_conn = None
            else:
                print(f"No connection (attempt {attempt + 1})")
        
        print("Failed to send input after 3 attempts")

    # ── xdotool helpers ──────────────────────────────────────────────

    def _xdotool(self, *args):
        """Run an xdotool command. Generic and works with any X11 app."""
        cmd = ['xdotool'] + list(args)
        env = os.environ.copy()
        env['DISPLAY'] = self._display
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                print(f"xdotool {' '.join(args)} failed (rc={result.returncode}): {result.stderr.strip()}")
        except Exception as e:
            print(f"xdotool error: {e}")

    def _focus_wine_window(self):
        """Focus the Wine application window so key/mouse events land correctly.

        Tries the configured WINDOW_TITLE first, then falls back to any Wine window.
        Uses --sync so xdotool waits until the window actually has focus.
        """
        env = os.environ.copy()
        env['DISPLAY'] = self._display
        for search_args in [
            ['search', '--name', self.window_title, 'windowfocus', '--sync'],
            ['search', '--class', 'Wine',            'windowfocus', '--sync'],
        ]:
            result = subprocess.run(
                ['xdotool'] + search_args, env=env,
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                print(f"xdotool focused window via {search_args[2]!r}")
                return
        print("Warning: could not focus Wine window — keys may not land")

    # ── App detection ────────────────────────────────────────────────

    def _is_starcraft(self) -> bool:
        return "starcraft" in self.app_file.lower() or "starcraft" in self.window_title.lower()

    # ── Input dispatch (no screen capture) ───────────────────────────

    def _send_action(self, action: WineAction):
        """Send input action without capturing a frame."""
        if self.input_method == "xdotool":
            self._step_xdotool(action)
        else:
            self._step_socket(action)

    # ── StarCraft navigation ──────────────────────────────────────────

    def _nav_screenshot(self, label: str):
        """Save a debug screenshot during navigation to /app/logs/nav_<label>.png."""
        try:
            frame = self._capture_screen()
            path = f"/app/logs/nav_{label}.png"
            cv2.imwrite(path, frame)
            print(f"Nav screenshot → {path}")
        except Exception as e:
            print(f"Nav screenshot failed ({label}): {e}")

    def _navigate_starcraft_to_game(self):
        """Navigate from StarCraft main menu to single-player custom game.

        Path: Main Menu → Single Player (s) → Expansion (e) → Profile (Return)
              → Episode Select → Play Custom (click) → AIIDE folder (click+Return)
              → Ok (click) → dismiss Tips (Return)
        """
        def key(k):
            self._focus_wine_window()
            self._send_action(WineAction(action_type="key", key=k))

        def click(x, y):
            self._focus_wine_window()
            self._send_action(WineAction(action_type="mouse", x=x, y=y,
                                         button="left", mouse_state="click"))

        self._nav_screenshot("00_main_menu")

        print("SC: pressing 's' for Single Player...")
        key("s")
        time.sleep(2)
        self._nav_screenshot("01_after_s")

        print("SC: pressing 'e' for Expansion...")
        key("e")
        time.sleep(2)
        self._nav_screenshot("02_after_e")

        print("SC: pressing Return to select profile...")
        key("Return")
        time.sleep(3)
        self._nav_screenshot("03_after_profile_return")

        print("SC: clicking 'Play Custom' (340, 420)...")
        click(340, 420)
        time.sleep(2)
        self._nav_screenshot("04_after_play_custom")

        print("SC: clicking AIIDE folder (100, 140)...")
        click(100, 140)
        time.sleep(0.5)
        key("Return")
        time.sleep(2)
        self._nav_screenshot("05_after_aiide_folder")

        print("SC: clicking 'Ok' to start game (540, 395)...")
        click(540, 395)
        print("SC: waiting for map to load (8s)...")
        time.sleep(8)
        self._nav_screenshot("06_after_map_load")

        print("SC: dismissing tips dialog...")
        key("Return")
        time.sleep(1)
        self._nav_screenshot("07_final")
        print("SC: navigation complete.")

    # ── StarCraft in-game verification ───────────────────────────────

    def _verify_starcraft_in_game(self, frame: np.ndarray) -> bool:
        """Return True if the screen looks like the StarCraft in-game view.

        The minimap (bottom-left corner) shows colorful terrain in-game but
        is uniform/dark on menu screens. We use pixel std-dev as the signal.
        """
        h, w = frame.shape[:2]
        # Minimap at 640x480 occupies roughly x:5-125, y:356-480
        x0 = max(0, int(5 * w / 640))
        x1 = max(1, int(125 * w / 640))
        y0 = max(0, int(356 * h / 480))
        y1 = h

        region = frame[y0:y1, x0:x1]
        if region.size == 0:
            return False

        std_dev = float(np.std(region))
        print(f"SC verify: minimap std_dev={std_dev:.1f} (threshold=15.0)")
        return std_dev > 15.0

    # ── Reset ────────────────────────────────────────────────────────

    def reset(self) -> WineObservation:
        """Reset environment and restart the Wine application.

        For StarCraft, also navigates from the main menu to a single-player
        custom game and returns a verified observation in metadata.
        """
        self._episode_id += 1
        self._step_count = 0

        try:
            print("Restarting Wine application...")
            result = subprocess.run(
                ['supervisorctl', '-s', 'http://127.0.0.1:9001', 'restart', 'wineapp'],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                print(f"✓ Wine application restarted: {result.stdout.strip()}")
                # StarCraft needs ~8s to reach the main menu; other apps need ~4s
                startup_wait = 8 if self._is_starcraft() else 4
                print(f"Waiting {startup_wait}s for startup...")
                time.sleep(startup_wait)
            else:
                print(f"Warning: Failed to restart wineapp: {result.stderr}")
        except Exception as e:
            print(f"Warning: Could not restart Wine application: {e}")

        if self.input_method == "socket":
            self._accept_input_connection()
            time.sleep(0.5)

        metadata: dict = {}
        if self._is_starcraft():
            self._navigate_starcraft_to_game()
            screen = self._capture_screen()
            verified = self._verify_starcraft_in_game(screen)
            metadata["game_screen_verified"] = verified
            if verified:
                print("✓ StarCraft in-game screen verified")
            else:
                print("Warning: could not verify StarCraft in-game screen after reset")
            return WineObservation(screen=screen, metadata=metadata)

        return WineObservation(screen=self._capture_screen())

    # ── Step dispatch ────────────────────────────────────────────────

    def step(self, action: WineAction) -> WineObservation:
        if self.input_method == "xdotool":
            self._step_xdotool(action)
        else:
            self._step_socket(action)
        
        self._step_count += 1
        return WineObservation(screen=self._capture_screen())

    # ── xdotool input (generic, works with any X11 app) ──────────────

    def _step_xdotool(self, action: WineAction):
        """Execute action using xdotool. Works with any X11 application."""
        if action.action_type in ("key", "keyboard"):
            key_name = _resolve_key(action.key)
            if not key_name:
                print(f"xdotool: Unknown key: {action.key}")
                return
            
            if action.key_state == "down":
                self._xdotool('keydown', key_name)
            elif action.key_state == "up":
                self._xdotool('keyup', key_name)
            else:
                self._xdotool('key', key_name)
                
        elif action.action_type == "mouse":
            x, y = action.x or 0.5, action.y or 0.5
            if x <= 1.0 and y <= 1.0:
                x, y = x * self.screen_width, y * self.screen_height
            x, y = int(x), int(y)
            
            button = '1' if (action.button or "left") == "left" else '3'
            
            if action.mouse_state == "move":
                self._xdotool('mousemove', str(x), str(y))
            elif action.mouse_state == "down":
                self._xdotool('mousemove', str(x), str(y))
                self._xdotool('mousedown', button)
            elif action.mouse_state == "up":
                self._xdotool('mousemove', str(x), str(y))
                self._xdotool('mouseup', button)
            elif not action.mouse_state or action.mouse_state == "click":
                self._xdotool('mousemove', str(x), str(y))
                self._xdotool('click', button)

    # ── Socket input (syncinput.exe) ─────────────────────────────────


    def _step_socket(self, action: WineAction):
        """Execute action via syncinput.exe TCP socket."""
        if action.action_type in ("key", "keyboard"):
            key_code = action.key or 0
            if isinstance(key_code, str):
                # Convert string key name to key code for syncinput
                _NAME_TO_CODE = {
                    'escape': 27, 'return': 13, 'enter': 13, 'tab': 9,
                    'backspace': 8, 'delete': 46, 'space': 32,
                    'up': 38, 'down': 40, 'left': 37, 'right': 39,
                }
                key_code = _NAME_TO_CODE.get(key_code.lower(), 0)
            
            key_state = action.key_state or "down"
            
            if key_state == "down" and 65 <= key_code <= 90:
                self._send_input(f"K{key_code},1|".encode())
                time.sleep(0.05)
                self._send_input(f"K{key_code},0|".encode())
            else:
                state = 1 if key_state == "down" else 0
                self._send_input(f"K{key_code},{state}|".encode())
                
        elif action.action_type == "mouse":
            is_left = 1 if (action.button or "left") == "left" else 0
            x, y = action.x or 0.5, action.y or 0.5
            if x <= 1.0 and y <= 1.0:
                x, y = x * self.screen_width, y * self.screen_height
            x, y = int(x), int(y)
            
            if not action.mouse_state or action.mouse_state == "click":
                self._send_input(f"M{is_left},1,{x},{y},{self.screen_width},{self.screen_height}|".encode())
                time.sleep(0.05)
                self._send_input(f"M{is_left},2,{x},{y},{self.screen_width},{self.screen_height}|".encode())
            else:
                state = 1 if action.mouse_state == "down" else 2
                self._send_input(f"M{is_left},{state},{x},{y},{self.screen_width},{self.screen_height}|".encode())
        
        time.sleep(0.2)

    # ── Screen capture ───────────────────────────────────────────────

    def _capture_screen(self) -> np.ndarray:
        """Capture screen using mss (fast in-memory)"""
        try:
            with mss.mss() as sct:
                monitor = {
                    "top": 0, "left": 0,
                    "width": self.screen_width, "height": self.screen_height,
                }
                sct_img = sct.grab(monitor)
                frame = np.array(sct_img)
                frame = frame[:, :, :3]  # Drop alpha channel (BGRA → BGR)
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
        if self.input_socket:
            try: self.input_socket.close()
            except: pass

    # ── Memory Reading ───────────────────────────────────────────────

    def find_process_pid(self, process_name: str) -> Optional[int]:
        """Find PID of a process by name (exact or partial)."""
        try:
            # simple pgrep
            # wine processes show up as:
            #   wine-preloader
            #   App.exe
            cmd = ['pgrep', '-f', process_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                # Return the last one (usually the child/actual app if multiples)
                # But typically we want the oldest? 
                # Let's try to be smart or just return the first.
                # Actually for wine, sometimes it's tricky.
                # Default to first found
                return int(pids[0])
        except Exception as e:
            print(f"find_process_pid error: {e}")
        return None

    def read_memory(self, pid: int, address: int, size: int) -> Optional[bytes]:
        """Read raw bytes from process memory via /proc/{pid}/mem."""
        mem_file = f"/proc/{pid}/mem"
        try:
            with open(mem_file, 'rb') as f:
                f.seek(address)
                return f.read(size)
        except Exception as e:
            print(f"read_memory error (PID {pid}, Addr {hex(address)}): {e}")
            return None

    def scan_memory(self, pid: int, value, value_type: str = "int", 
                   start_addr: int = 0x00400000, end_addr: int = 0x7FFFFFFF,
                   step: int = 4) -> list[int]:
        """
        Scan memory for a value.
        Very naive implementation: reads chunks and searches.
        value_type: 'int' (4 bytes), 'short' (2 bytes), 'byte' (1 byte), 'string'
        """
        found_addresses = []
        chunk_size = 1024 * 1024  # 1MB chunks
        
        # Determine struct format
        fmt = 'I' # unsigned int
        data_len = 4
        target_bytes = b''
        
        if value_type == 'int':
            fmt = 'I' # unsigned int 32-bit
            data_len = 4
            target_bytes = struct.pack(fmt, int(value))
        elif value_type == 'short':
            fmt = 'H' # unsigned short 16-bit
            data_len = 2
            target_bytes = struct.pack(fmt, int(value))
        elif value_type == 'byte':
            fmt = 'B' # unsigned char 8-bit
            data_len = 1
            target_bytes = struct.pack(fmt, int(value))
        elif value_type == 'string':
            target_bytes = value.encode('utf-8')
            data_len = len(target_bytes)
        
        print(f"Scanning PID {pid} for {value} ({value_type}) [{target_bytes.hex()}]...")
        
        try:
            # We need to read /proc/pid/maps to know valid ranges
            with open(f"/proc/{pid}/maps", 'r') as map_f:
                maps = map_f.readlines()
                
            mem_file = f"/proc/{pid}/mem"
            with open(mem_file, 'rb') as mem_f:
                for line in maps:
                    parts = line.split()
                    # Parse address range: 00400000-00401000
                    addr_range = parts[0].split('-')
                    range_start = int(addr_range[0], 16)
                    range_end = int(addr_range[1], 16)
                    perms = parts[1]
                    
                    # Skip if not readable
                    if 'r' not in perms: continue
                    # Skip shared libs or stack/heap if requested (optimization)
                    # For now scan everything readable
                    
                    # Optimization: only scan if within requested global bounds
                    if range_end < start_addr or range_start > end_addr:
                        continue
                        
                    # Clamp to requested bounds
                    curr_ptr = max(range_start, start_addr)
                    limit = min(range_end, end_addr)
                    
                    if curr_ptr >= limit: continue

                    # Seek to start of this region
                    try:
                        mem_f.seek(curr_ptr)
                    except:
                        continue
                        
                    # Read in chunks
                    while curr_ptr < limit:
                        read_size = min(chunk_size, limit - curr_ptr)
                        try:
                            chunk = mem_f.read(read_size)
                        except:
                            break # Region might not be fully readable
                            
                        # Search in chunk
                        offset = 0
                        while True:
                            idx = chunk.find(target_bytes, offset)
                            if idx == -1:
                                break
                            
                            found_addr = curr_ptr + idx
                            found_addresses.append(found_addr)
                            
                            # Move past this match
                            offset = idx + 1
                            
                            # Limit results to avoid massive spam
                            if len(found_addresses) > 100:
                                return found_addresses

                        curr_ptr += read_size
                        
        except Exception as e:
            print(f"Scan error: {e}")
            
        return found_addresses
