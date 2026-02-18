import re

def perform_action(action_data):
    print(f"Testing Action: {action_data}")
    match = re.search(r"MOVE:\s*(\d+)\s+(\d+)\s+(left|right)", action_data, re.IGNORECASE)
    
    if match:
        row = int(match.group(1))
        col = int(match.group(2))
        button = match.group(3).lower()
        
        # Coordinate Transformation for WinMine (Green)
        # From solve_minesweeper_llm.py
        GRID_X = 5
        GRID_Y = 25
        CELL_W = 18
        CELL_H = 21
        
        # Calculate Pixel Center
        x = int(GRID_X + (col * CELL_W) + (CELL_W / 2))
        y = int(GRID_Y + (row * CELL_H) + (CELL_H / 2))
        
        print(f"  Row {row}, Col {col} -> Pixel ({x}, {y})")
        
        # WinMine XP (Standard) check
        # Grid typically starts at (12, 55)?
        # solve_minesweeper.py says: GRID_X0 = 12, GRID_Y0 = 55. Cell Size = 16.
        # solve_minesweeper_llm.py says: GRID_X = 5, GRID_Y = 25. Cell Size = 18x21.
        
        print("\n  COMPARISON:")
        print(f"  LLM Script Config: Start({GRID_X},{GRID_Y}), Size({CELL_W}x{CELL_H})")
        print("  WinMine (Standard) Config: Start(12,55), Size(16x16)")
        
        if GRID_X == 5 and CELL_W == 18:
             print("  WARNING: The LLM script seems to be configured for a different Minesweeper version (maybe gnome-mines?)")
             print("  WineMine uses 16x16 cells and starts further down.")
             
        return x, y
    else:
        print("  No Match")
        return None

print("Test 1: Top-Left (0, 0)")
perform_action("Analysis: test\nMOVE: 0 0 left")

print("\nTest 2: Middle (4, 4)")
perform_action("Analysis: test\nMOVE: 4 4 right")
