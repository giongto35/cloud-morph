#!/usr/bin/env python3
"""
Minesweeper Solver via OpenEnv API.

Runs locally and interacts with WineMine through the OpenEnv HTTP API.
Uses xdotool input method (via the API) for mouse clicks and keyboard.

Usage:
    python3 solve_minesweeper.py [--api http://localhost:8000] [--games N]
"""

import requests
import base64
import time
import random
import argparse
import sys
import numpy as np
import cv2

API_BASE = "http://localhost:8000"

# ── Grid constants for WineMine Beginner (9x9, 10 mines) ────────────
GRID_ROWS = 9
GRID_COLS = 9
TOTAL_MINES = 10
CELL_SIZE = 16      # pixels per cell

# These will be updated by auto_calibrate
GRID_X0 = 12        # grid left edge in screen pixels
GRID_Y0 = 55        # grid top edge in screen pixels
SMILEY_X = 76       # smiley button center X
SMILEY_Y = 36       # smiley button center Y

CALIBRATED = False

# Cell states
UNKNOWN = -2
FLAG = -1
EMPTY = 0
# 1-8 = number of adjacent mines


def step(action: dict) -> dict:
    """Send an action to the OpenEnv API and return the observation."""
    try:
        r = requests.post(f"{API_BASE}/step", json=action, timeout=10)
        return r.json()
    except Exception as e:
        print(f"API Error: {e}")
        sys.exit(1)


def get_screen_rgb() -> np.ndarray:
    """Capture screen as RGB numpy array (H, W, 3)."""
    # Move mouse away to avoid obscuring grid
    obs = step({"action_type": "mouse", "x": 790, "y": 590, "mouse_state": "move"})
    img_bytes = base64.b64decode(obs["observation"]["screen"])
    # Decode JPEG to numpy
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # BGR
    return img


def click(x: int, y: int, button: str = "left"):
    """Click at absolute pixel coordinates."""
    step({"action_type": "mouse", "x": x, "y": y, "button": button, "mouse_state": "click"})


def cell_center(row: int, col: int) -> tuple:
    """Get screen pixel coordinates for the center of a grid cell."""
    x = GRID_X0 + col * CELL_SIZE + CELL_SIZE // 2
    y = GRID_Y0 + row * CELL_SIZE + CELL_SIZE // 2
    return x, y


def new_game():
    """Start a new game by pressing F2."""
    step({"action_type": "key", "key": "F2"})
    time.sleep(0.5)


def auto_calibrate(img: np.ndarray):
    """Calibrate Grid position by scanning for the first green pixel."""
    global GRID_X0, GRID_Y0
    
    # 1. Find Y0: Scan vertical line at x=20 (approx first col center)
    found_y = None
    for y in range(30, 80):
        if y >= img.shape[0]: break
        pixel = img[y, 20] # BGR
        b, g, r = int(pixel[0]), int(pixel[1]), int(pixel[2])
        # Look for green background (G > 90) start
        if g > 90 and g > r + 30:
            found_y = y
            break
            
    # 2. Find X0: Scan horizontal line at found_y + 8 (approx first row center)
    found_x = None
    if found_y:
        scan_y = found_y + 8
        for x in range(0, 40):
            if scan_y >= img.shape[0] or x >= img.shape[1]: break
            pixel = img[scan_y, x]
            b, g, r = int(pixel[0]), int(pixel[1]), int(pixel[2])
            if g > 90 and g > r + 30:
                found_x = x
                break
    
    if found_x is not None and found_y is not None:
        print(f"Auto-calibrated Grid: X0={found_x}, Y0={found_y}")
        GRID_X0 = found_x
        GRID_Y0 = found_y
    else:
        print(f"Calibration failed, using defaults: X0={GRID_X0}, Y0={GRID_Y0}")


def classify_cell(cell: np.ndarray) -> int:
    h, w = cell.shape[:2]
    
    # Check for Flag first (Red icon on covered cell)
    # Use Robust Red relative check: R > 100, R > G + 20, R > B + 20
    # Sample wider center area 8x8
    center = cell[4:12, 4:12]
    
    # Robust Red check: R > 100, R > G + 20, R > B + 20
    center_r = center[:,:,2]
    center_g = center[:,:,1]
    center_b = center[:,:,0]
    
    red_pixel_mask = (center_r > 100) & (center_r > center_g + 20) & (center_r > center_b + 20)
    if np.sum(red_pixel_mask) > 2:
        return FLAG
        
    # Check for Question Mark (Cyan on Green) - treat as FLAG to stop toggling
    # Cyan: High Blue, High Green, Low Red
    cyan_pixel_mask = (center_b > 80) & (center_g > 80) & (center_r < 60)
    if np.sum(cyan_pixel_mask) > 2:
        return FLAG

    # Main Discriminator: Background Green Intensity
    # Sample tight center 6x6 to avoid bevel borders
    bg_sample = cell[5:11, 5:11]
    avg_b, avg_g, avg_r = np.mean(bg_sample, axis=(0, 1))

    # Covered cells: Bright Green (G > 80) AND greener than red (G - R > 60)
    # Revealed empty: Darker Green (G < 75)
    if avg_g > 80 and (avg_g - avg_r) > 60:
        return UNKNOWN
    
    # If falling through, it is Revealed (Empty or Number).
    # ID the number by color count in center 10x10 area
    detail = cell[3:13, 3:13]
    d_b, d_g, d_r = detail[:,:,0], detail[:,:,1], detail[:,:,2]
    
    # 1 (Blue): High Blue
    mask_1 = (d_b > 100) & (d_b > d_r + 40)
    if np.sum(mask_1) > 2: return 1
    
    # 2 (Cyan/Green): High Green (against dark bg)
    mask_2 = (d_g > 130) & (d_r < 100)
    if np.sum(mask_2) > 2: return 2
    
    # 3 (Red): High Red
    mask_3 = (d_r > 130) & (d_r > d_g + 30)
    if np.sum(mask_3) > 2: return 3
    
    # 4 (Dark Blue): Moderate Blue, low RG
    mask_4 = (d_b > 80) & (d_r < 60) & (d_g < 60)
    if np.sum(mask_4) > 2: return 4
    
    # 5 (Maroon): Low-Mid Red
    mask_5 = (d_r > 80) & (d_g < 50) & (d_b < 50)
    if np.sum(mask_5) > 2: return 5
    
    # 6 (Teal): High G+B
    mask_6 = (d_g > 80) & (d_b > 80) & (d_r < 50)
    if np.sum(mask_6) > 2: return 6

    # 7 (Black/Dark) - skipped for now
    # 8 (Gray) - skipped for now

    return EMPTY


def parse_board(img: np.ndarray) -> np.ndarray:
    """Parse the WineMine grid from a screenshot into a board array."""
    board = np.full((GRID_ROWS, GRID_COLS), UNKNOWN, dtype=int)
    
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            x0 = GRID_X0 + c * CELL_SIZE
            y0 = GRID_Y0 + r * CELL_SIZE
            x1 = x0 + CELL_SIZE
            y1 = y0 + CELL_SIZE
            
            if y1 > img.shape[0] or x1 > img.shape[1]:
                continue
            
            cell = img[y0:y1, x0:x1]  # BGR
            board[r, c] = classify_cell(cell)
    
    return board


def print_board(board: np.ndarray):
    """Pretty-print the board state."""
    symbols = {UNKNOWN: ".", FLAG: "F", EMPTY: " "}
    print("  " + " ".join(str(c) for c in range(GRID_COLS)))
    print("  " + "-" * (GRID_COLS * 2 - 1))
    for r in range(GRID_ROWS):
        row_str = ""
        for c in range(GRID_COLS):
            v = board[r, c]
            row_str += symbols.get(v, str(v)) + " "
        print(f"{r}|{row_str}")


def get_neighbors(r: int, c: int) -> list:
    """Get valid neighbor coordinates."""
    neighbors = []
    for dr in [-1, 0, 1]:
        for dc in [-1, 0, 1]:
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < GRID_ROWS and 0 <= nc < GRID_COLS:
                neighbors.append((nr, nc))
    return neighbors


def solve_step(board: np.ndarray) -> list:
    """Apply constraint-based solving to find safe moves."""
    moves = []
    
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            val = board[r, c]
            if val <= 0:  # Only process numbered cells
                continue
            
            neighbors = get_neighbors(r, c)
            unknowns = [(nr, nc) for nr, nc in neighbors if board[nr, nc] == UNKNOWN]
            flags = sum(1 for nr, nc in neighbors if board[nr, nc] == FLAG)
            
            effective = val - flags
            
            # Rule 1: All mines accounted for → remaining unknowns are safe
            if effective == 0 and unknowns:
                for nr, nc in unknowns:
                    if (nr, nc, "left") not in moves:
                        moves.append((nr, nc, "left"))
            
            # Rule 2: Remaining unknowns == remaining mines → all are mines
            elif effective > 0 and effective == len(unknowns):
                for nr, nc in unknowns:
                    # Don't re-flag if we already see a flag.
                    # But board[nr,nc] is UNKNOWN here.
                    if (nr, nc, "right") not in moves:
                        moves.append((nr, nc, "right"))
    
    return moves


def guess_move(board: np.ndarray) -> tuple:
    """Make an educated guess when constraint solving is stuck."""
    unknowns = []
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            if board[r, c] == UNKNOWN:
                unknowns.append((r, c))
    
    if not unknowns:
        return None
    
    # Score unknowns: prefer cells adjacent to fewer numbered cells
    best = []
    best_score = 999
    
    for r, c in unknowns:
        neighbors = get_neighbors(r, c)
        adj_numbers = sum(1 for nr, nc in neighbors if board[nr, nc] > 0)
        if adj_numbers < best_score:
            best_score = adj_numbers
            best = [(r, c)]
        elif adj_numbers == best_score:
            best.append((r, c))
    
    chosen = random.choice(best)
    return (chosen[0], chosen[1], "left")


def is_won(board: np.ndarray) -> bool:
    """Check if all non-mine cells are revealed."""
    unknown_count = np.sum(board == UNKNOWN)
    flag_count = np.sum(board == FLAG)
    return (unknown_count + flag_count) == TOTAL_MINES


def is_dead(img: np.ndarray) -> bool:
    """Check for revealed mines (Red background)."""
    # Check screen for any red cell (Mine exploded)
    # Scan cell centers for red background
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            x = GRID_X0 + c * CELL_SIZE + 8
            y = GRID_Y0 + r * CELL_SIZE + 8
            if y >= img.shape[0] or x >= img.shape[1]: continue
            
            pixel = img[y, x] # BGR
            # Exploded mine is Bright Red
            if pixel[2] > 150 and pixel[1] < 80:
                return True
    return False


def solve_game(game_num: int = 1) -> bool:
    """Solve one game of Minesweeper. Returns True if won."""
    print(f"\n{'='*50}")
    print(f"Game {game_num}: Starting new game")
    print(f"{'='*50}")
    
    new_game()
    global CALIBRATED
    if False and not CALIBRATED: # Auto-calibration Disabled
        img = get_screen_rgb()
        auto_calibrate(img)
        CALIBRATED = True
    
    # First click: click center
    first_r, first_c = GRID_ROWS // 2, GRID_COLS // 2
    x, y = cell_center(first_r, first_c)
    print(f"First click at cell ({first_r}, {first_c})")
    click(x, y)
    time.sleep(0.5)
    
    max_steps = 100
    for step_num in range(max_steps):
        # Capture and parse
        img = get_screen_rgb()
        
        if is_dead(img):
            print(f"\n💀 DEAD at step {step_num}!")
            board = parse_board(img)
            print_board(board)
            return False
        
        board = parse_board(img)
        
        if is_won(board):
            print(f"\n🎉 WON at step {step_num}!")
            print_board(board)
            return True
        
        if step_num % 5 == 0:
            print(f"\n--- Step {step_num} ---")
            print_board(board)
        
        moves = solve_step(board)
        
        if moves:
            safe_moves = [m for m in moves if m[2] == "left"]
            flag_moves = [m for m in moves if m[2] == "right"]
            
            if flag_moves:
                print(f"  Flagging {len(flag_moves)} mines: {[(r,c) for r,c,_ in flag_moves]}")
                for r, c, btn in flag_moves:
                    x, y = cell_center(r, c)
                    click(x, y, button="right")
                    time.sleep(0.15)
            
            if safe_moves:
                print(f"  Clicking {len(safe_moves)} safe cells")
                for r, c, btn in safe_moves:
                    x, y = cell_center(r, c)
                    click(x, y, button="left")
                    time.sleep(0.15)
        else:
            guess = guess_move(board)
            if guess is None:
                # Board might be solved or we are stuck
                if is_won(board):
                     print(f"\n🎉 WON at step {step_num}!")
                     return True
                break
            
            r, c, btn = guess
            print(f"  🎲 Guessing at ({r}, {c})")
            x, y = cell_center(r, c)
            click(x, y, button=btn)
            time.sleep(0.5)
    
    print("⏱ Timed out")
    return False


def main():
    global API_BASE
    parser = argparse.ArgumentParser(description="Solve Minesweeper via OpenEnv API")
    parser.add_argument("--api", default=API_BASE, help="OpenEnv API URL")
    parser.add_argument("--games", type=int, default=1, help="Number of games to play")
    args = parser.parse_args()
    
    API_BASE = args.api
    
    try:
        r = requests.get(f"{API_BASE}/health", timeout=5)
        print(f"API health: {r.status_code}")
    except Exception as e:
        print(f"ERROR: Cannot reach API at {API_BASE}: {e}")
        sys.exit(1)
    
    wins = 0
    for i in range(1, args.games + 1):
        if solve_game(i):
            wins += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {wins}/{args.games} games won")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
