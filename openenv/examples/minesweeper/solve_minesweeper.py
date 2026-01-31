
import os
import sys
import time
import random
import cv2
import numpy as np
from collections import deque

# Ensure we can import server modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server.wine_environment import WineEnvironment
from models import WineAction

# Constants for Cell States
UNKNOWN = -2
FLAG = -1
EMPTY = 0
# numbers 1-8 are themselves

class MinesweeperSolver:
    def __init__(self):
        self.env = WineEnvironment(
            screen_width=int(os.getenv("SCREEN_WIDTH", "800")),
            screen_height=int(os.getenv("SCREEN_HEIGHT", "600")),
        )
        self.visited = set() # Track clicked cells to avoid loops
        # Grid settings for Gnome Mines Small
        self.grid_w = 8
        self.grid_h = 8
        self.cell_size = 24 # Placeholder (will be updated by detect_grid_params)
        self.board_x = 0
        self.board_y = 0

    def match_cell(self, cell_img):
        # Heuristic Matching
        h, w, _ = cell_img.shape
        cy, cx = h//2, w//2
        center = cell_img[cy-4:cy+4, cx-4:cx+4]
        avg = np.mean(center, axis=(0,1))
        b, g, r = avg
        std = np.std(cell_img)
        
        # Log stats for debug (sometimes)
        # print(f"Cell stats: B={b:.1f} G={g:.1f} R={r:.1f} Std={std:.1f}")

        if b > r + 30 and b > g + 10: return 1
        if g > r + 30 and g > b + 10: return 2
        if r > b + 30 and r > g + 30: return 3
        
        # Covered vs Empty
        # Assuming revealed empty is flatter or specific color
        if std < 25:
            return EMPTY
            
        return UNKNOWN

    def detect_grid_params(self, frame):
        # reuse CV logic from extract_templates
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # roi top 400x400
        roi = gray[0:400, 0:400]
        edges = cv2.Canny(roi, 50, 150)
        kernel = np.ones((5,5), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=1)
        cnts, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)
        
        if cnts:
            x, y, w, h = cv2.boundingRect(cnts[0])
            # Assuming 8x8 small grid + header
            # Header approx 45px?
            grid_y = y + 45
            grid_h_real = h - 45
            self.cell_size = grid_h_real // self.grid_h
            self.board_x = x
            self.board_y = grid_y
            print(f"Detected Grid: x={x}, y={grid_y}, cell_size={self.cell_size}")
            return True
        return False

    def parse_board(self, frame):
        if self.board_x == 0:
            if not self.detect_grid_params(frame):
                return np.full((self.grid_h, self.grid_w), UNKNOWN)

        board = np.zeros((self.grid_h, self.grid_w), dtype=int)
        
        for r in range(self.grid_h):
            for c in range(self.grid_w):
                cx = self.board_x + c * self.cell_size
                cy = self.board_y + r * self.cell_size
                
                # Safety crop
                if cy+self.cell_size > frame.shape[0] or cx+self.cell_size > frame.shape[1]:
                    continue
                    
                cell_img = frame[cy:cy+self.cell_size, cx:cx+self.cell_size]
                board[r,c] = self.match_cell(cell_img)
                
        return board

    def get_neighbors(self, r, c):
        n = []
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0: continue
                nr, nc = r+dr, c+dc
                if 0 <= nr < self.grid_h and 0 <= nc < self.grid_w:
                    n.append((nr, nc))
        return n

    def get_move(self, board):
        # 1. Constraint Satisfaction
        # Identify all number cells
        moves = []
        flags = []
        
        # Helper lists
        known_flags = set()
        for r in range(self.grid_h):
            for c in range(self.grid_w):
                if board[r,c] == FLAG:
                    known_flags.add((r,c))

        progress = False
        
        for r in range(self.grid_h):
            for c in range(self.grid_w):
                val = board[r,c]
                if val > 0: # Number cell
                    neighbors = self.get_neighbors(r, c)
                    unknown_neighbors = []
                    flag_neighbors_count = 0
                    
                    for nr, nc in neighbors:
                        if board[nr,nc] == UNKNOWN:
                            unknown_neighbors.append((nr,nc))
                        elif board[nr,nc] == FLAG:
                            flag_neighbors_count += 1
                                    
                    effective_val = val - flag_neighbors_count
                    
                    # Rule 1: If effective value is 0, all unknowns are SAFE
                    if effective_val == 0:
                        for nr, nc in unknown_neighbors:
                            if (nr, nc) not in [m[0:2] for m in moves]:
                                moves.append((nr, nc, "left"))
                                progress = True

                    # Rule 2: If effective value == count(unknowns), all unknowns are MINES
                    elif effective_val == len(unknown_neighbors):
                        for nr, nc in unknown_neighbors:
                            if (nr, nc) not in known_flags: # Avoid re-flagging
                                moves.append((nr, nc, "right"))
                                known_flags.add((nr, nc)) # Mark locally
                                progress = True
        
        if moves:
            # Return first move (or all? Solver loop handles one step usually)
            return moves[0]

        # 2. Heuristic / Random (if stuck)
        unknowns = []
        for r in range(self.grid_h):
            for c in range(self.grid_w):
                if board[r,c] == UNKNOWN and (r,c) not in known_flags and (r,c) not in self.visited:
                   unknowns.append((r,c))
                    
        if not unknowns:
            print("No moves left.")
            return None # Solved?

        # Prefer corner if start, or random
        print("Solver stuck, guessing...")
        r, c = random.choice(unknowns)
        return (r, c, "left")

    def run(self):
        print("Starting Solver Loop...")
        # Initial click to start
        print("Starting Solver Loop...")
        # Initial click to start (Click Smiley Face to reset)
        # Coords approx (216, 90) -> (0.27, 0.15)
        print("Clicking New Game (Smiley)...")
        action = WineAction(action_type="mouse", x=0.27, y=0.15, button="left", mouse_state="down")
        self.env.step(action)
        time.sleep(0.1)
        action.mouse_state = "up"
        self.env.step(action)
        time.sleep(1)
        
        # Click center board to ensure focus/start
        action = WineAction(action_type="mouse", x=0.25, y=0.33, button="left", mouse_state="down")
        self.env.step(action)
        time.sleep(0.1)
        action.mouse_state = "up"
        self.env.step(action)
        time.sleep(1)
        
        step = 0
        while step < 100:
            frame = self.env._capture_screen()
            board = self.parse_board(frame)
            
            move = self.get_move(board)
            if not move:
                print("No moves left or solved.")
                break
                
            r, c, btn = move
            print(f"Move {step}: {btn} click at ({r}, {c})")
            
            # Convert grid to screen
            sx = (self.board_x + c * self.cell_size + self.cell_size / 2) / self.env.screen_width
            sy = (self.board_y + r * self.cell_size + self.cell_size / 2) / self.env.screen_height
            
            action = WineAction(action_type="mouse", x=sx, y=sy, button=btn, mouse_state="down")
            self.env.step(action)
            time.sleep(0.1)
            action.mouse_state = "up"
            self.env.step(action)
            
            if step % 10 == 0:
                cv2.imwrite(f"/app/logs/debug_step_{step:03d}.png", frame)
            
            if btn == "left":
                self.visited.add((r, c))
            
            time.sleep(1)
            step += 1

if __name__ == "__main__":
    solver = MinesweeperSolver()
    solver.run()
