import cv2
import numpy as np

def analyze_grid():
    # Load the screenshot
    img_path = "/Users/giongto35/code/cloud-morph/openenv/calibration.png"
    img = cv2.imread(img_path)
    if img is None:
        print("Error loading image")
        return

    # Convert to grayscale for edge detection
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # WinMine cells have a 3D bevel. 
    # Unrevealed cells are distinct Green.
    # Let's find the smiley face first to anchor ? No, grid is better.
    
    # WinMine grid usually starts with a dark border.
    # Let's simple print pixel values at expected locations to debug.
    
    # Expected Grid: 8x8 (Beginner)
    # Window Top-Left is likely (0,0) in the screenshot? No, fluxbox decorations.
    
    # 1. Detect the main window area (Grey background)
    # The screenshot shows the full viewer.
    
    # Let's assume the window is at top-left.
    # Crop to top-left 300x300
    crop = img[0:300, 0:300]
    
    # Save crop for inspection
    cv2.imwrite("debug_crop.png", crop)
    
    # Find the green cells.
    # Green unrevealed in WinMine is roughly RGB(0, 128, 0) or similar?
    # In the screenshot it looked textured green.
    
    # Mask for green
    # HSV?
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    # Green range
    lower_green = np.array([40, 50, 50])
    upper_green = np.array([80, 255, 255])
    mask = cv2.inRange(hsv, lower_green, upper_green)
    
    # Find contours or bounding box of the green area
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # Get bounding box of all green
        all_points = np.vstack(contours)
        x, y, w, h = cv2.boundingRect(all_points)
        print(f"Green Area Bounds: x={x}, y={y}, w={w}, h={h}")
        
        # Calculate cell size
        # 8x8 grid
        cell_w = w / 8.0
        cell_h = h / 8.0
        print(f"Estimated Cell Size: {cell_w} x {cell_h}")
        
        # Grid Offset (relative to image 0,0)
        print(f"Grid Offset X: {x}")
        print(f"Grid Offset Y: {y}")
        
        # Center of first cell (0,0)
        c00_x = x + cell_w/2
        c00_y = y + cell_h/2
        print(f"Cell 0,0 Center: {c00_x}, {c00_y}")
        
        # Color of unrevealed cell
        # Sample center of 0,0
        sample = crop[int(c00_y), int(c00_x)]
        print(f"Unrevealed Color (BGR): {sample}")

analyze_grid()
