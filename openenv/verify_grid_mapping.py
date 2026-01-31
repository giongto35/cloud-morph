import cv2
import numpy as np
import os

def draw_grid_overlay():
    # Load the latest turn image or calibration image
    img_path = "turn.png"
    if not os.path.exists(img_path):
        img_path = "calibration.png"
        
    print(f"Loading {img_path}...")
    img = cv2.imread(img_path)
    if img is None:
        print("Failed to load image.")
        return

    # Calibration Constants (from solve_minesweeper_llm.py)
    GRID_X = 5
    GRID_Y = 25
    CELL_W = 18
    CELL_H = 21
    ROWS = 9
    COLS = 9
    
    # Draw Vertical Lines (Cols)
    for c in range(COLS + 1):
        x = GRID_X + (c * CELL_W)
        start_y = GRID_Y
        end_y = GRID_Y + (ROWS * CELL_H)
        cv2.line(img, (x, start_y), (x, end_y), (0, 255, 255), 1) # Yellow lines

    # Draw Horizontal Lines (Rows)
    for r in range(ROWS + 1):
        y = GRID_Y + (r * CELL_H)
        start_x = GRID_X
        end_x = GRID_X + (COLS * CELL_W)
        cv2.line(img, (start_x, y), (end_x, y), (0, 255, 255), 1) # Yellow lines

    # Draw Center Points (target clicks)
    for r in range(ROWS):
        for c in range(COLS):
            cx = int(GRID_X + (c * CELL_W) + (CELL_W / 2))
            cy = int(GRID_Y + (r * CELL_H) + (CELL_H / 2))
            cv2.circle(img, (cx, cy), 2, (0, 0, 255), -1) # Red dots

    output_path = "debug_grid_overlay.png"
    cv2.imwrite(output_path, img)
    print(f"Saved grid overlay to {output_path}")

if __name__ == "__main__":
    draw_grid_overlay()
