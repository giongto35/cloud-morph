
import requests
import json
import base64
import time
import base64
import time
import subprocess
import os
import sys
import cv2
import numpy as np

API_URL = "http://localhost:8000"

def get_screenshot():
    # Execute a no-op action to get the current state
    # or use /reset if starting fresh, but here we assume ongoing
    # Using "move" with same coords or neutral
    payload = {
        "action_type": "mouse",
        "mouse_state": "move",
        "x": 0.5,
        "y": 0.5,
        "metadata": {}
    }
    try:
        res = requests.post(f"{API_URL}/step", json=payload)
        res.raise_for_status()
        data = res.json()
        b64_img = data["observation"]["screen"]
        return b64_img
    except Exception as e:
        print(f"Error getting screenshot: {e}")
        return None

def save_image(b64_img, filename="turn.png"):
    # Decode
    img_data = base64.b64decode(b64_img)
    np_arr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    # Resize to max 300x300 for speed
    height, width = img.shape[:2]
    max_dim = 300
    if height > max_dim or width > max_dim:
        scale = max_dim / max(height, width)
        new_width = int(width * scale)
        new_height = int(height * scale)
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
    
    # Save
    cv2.imwrite(filename, img)
    return os.path.abspath(filename)

def save_debug_click_image(image_path, x, y, filename="debug_click.png"):
    try:
        # Read with cv2
        img = cv2.imread(image_path)
        if img is None: return None
        
        # Draw Red Circle (BGR: 0, 0, 255)
        cv2.circle(img, (x, y), 5, (0, 0, 255), 2)
        # Draw Crosshair
        cv2.line(img, (x-10, y), (x+10, y), (0, 0, 255), 1)
        cv2.line(img, (x, y-10), (x, y+10), (0, 0, 255), 1)
        
        cv2.imwrite(filename, img)
        return os.path.abspath(filename)
    except Exception as e:
        print(f"Failed to save debug image: {e}")
        return None

import re

def ask_claude(image_path, previous_action=None, screen_changed=None):
    print("Picking move...")
    
    feedback_section = ""
    if previous_action:
        status = "Screen Changed" if screen_changed else "NO CHANGE (Move likely failed)"
        feedback_section = f"""
PREVIOUS ACTION: {previous_action}
RESULT: {status}
"""
        if not screen_changed:
            feedback_section += "WARNING: Your last move did not affect the board. Check your coordinates or click type.\n"

    prompt = f"""
[Image]
ROLE: You are an expert Minesweeper playing agent.
TASK: Analyze the board and output the next move.

STRATEGY:
1. Look for "Low Hanging Fruit": Zones where a number touches exactly that many unrevealed cells (e.g. a "1" touching 1 unrevealed cell -> It's a MINE).
2. Look for "Safe Cells": If a number's mines are all found, all other neighbors are SAFE.
3. Use Patterns: 1-2-1 pattern, 1-2-2-1 pattern.
4. If stuck, guess a corner or edge of an unrevealed block, or a cell with low probability of being a mine.

FORMAT REQUIREMENTS:
1. You MUST provide reasoning first. Explain WHY you are choosing a cell.
2. You MUST end your response with EXACTLY: "MOVE: ROW COL TYPE"

EXAMPLE RESPONSE:
Analysis: The "1" at Row 2, Col 3 touches only one unrevealed cell at (2, 4). This must be a mine. I will flag it.
MOVE: 2 4 right

EXAMPLE RESPONSE 2:
Analysis: The "1" at (0, 0) already has a flag next to it. The other neighbor (0, 1) must be safe.
MOVE: 0 1 left

NOTE: The image is 800x600. The board is in the top-left area.
NOTE: The board uses the "WineMine" theme, so cells are GREEN blocks.
NOTE: Output 0-indexed coordinates. Row 0 is top, Col 0 is left.

{feedback_section}
CRITICAL: The game is ONLY WON if the smiley face is wearing SUNGLASSES (Cool Smiley). 
CRITICAL: If the smiley face is yellow with a normal smile, the game is ONGOING. Do NOT output GAME WON.
CRITICAL: If the game is LOST, the smiley will have X eyes or be a dead face.
CRITICAL: If the game is ONGOING, output the move in "MOVE: ROW COL TYPE" format.
CRITICAL: Do NOT click on revealed cells (Numbers, Empty/Black space). 
CRITICAL: ONLY click on UNREVEALED GREEN BLOCKS. Clicking a number does nothing.
    """
    
    # Debug: Print prompt (optional, but requested)
    # print(f"--- Prompt ---\n{prompt}\n----------------")

    # Combine text prompt and image path into a SINGLE argument
    # WE USE DIRECT BASE64 INJECTION TO AVOID CLI FILE PERMISSION PROMPTS
    
    # 1. Read the resized image file to get base64
    with open(image_path, "rb") as img_file:
        b64_str = base64.b64encode(img_file.read()).decode('utf-8')
        
    full_prompt = f"{prompt}\n\n[Image Data Base64]:\ndata:image/png;base64,{b64_str}\n\n(Please interpret the above base64 data as the game board image)"

    
    try:
        result = subprocess.run(
            ["claude", "-p", full_prompt],
            capture_output=True,
            text=True,
            timeout=120 # Increased timeout even more
        )
        if result.returncode != 0:
            print(f"\n[CLAUDE ERROR]: Return Code {result.returncode}")
            print(f"Stderr: {result.stderr}")
            return None
            
        output = result.stdout.strip()
        
        # requested debug print
        print(f"\n[CLAUDE RESPONSE]:\n{output}\n------------------")
        
        return output
    except Exception as e:
        print(f"\nSubprocess error: {e}")
        return None

def perform_action(action_data):
    if not action_data: return False, None
    
    # 0. Check for Game Over logic
    if "GAME WON" in action_data.upper():
        print("\n!!! GAME WON DETECTED by LLM !!!")
        return False, "WON"
        
    if "GAME LOST" in action_data.upper() or "GAME OVER" in action_data.upper():
        print("\n!!! GAME LOST DETECTED by LLM !!!")
        return False, "LOST"
    
    # 1. Try to parse MOVE: ROW COL format (Strict to avoid parsing reasoning numbers)
    match = re.search(r"MOVE:\s*(\d+)\s+(\d+)\s+(left|right)", action_data, re.IGNORECASE)
    
    # 2. Fallback: Check if it looks like an initial state description or refusal
    if not match:
        print("-> Could not parse 'MOVE:' command. Checking for fallback...")
        if "initial" in action_data.lower() or "unrevealed" in action_data.lower() or "00:00" in action_data:
            print("-> Detected Initial State loop. FORCING API CLICK (New Game).")
            # Force Smiley Click (Center Top)
            # Smiley is roughly at X=75, Y=55 based on analysis
            x, y, button = 75, 55, "left"
            match = True # Fake match
            # Send directly
            payload = {"action_type": "mouse", "x": x, "y": y, "button": button, "mouse_state": "click"}
            try:
                requests.post(f"{API_URL}/step", json=payload)
            except: pass
            return True, "Forced Smiley Click"
        else:
             print("-> No move found.")
             return False, None

    if match and isinstance(match, re.Match):
        row = int(match.group(1))
        col = int(match.group(2))
        button = match.group(3).lower()
        
        # Coordinate Transformation for WinMine (Green)
        # Grid Start: (12, 55)
        # Cell Size: 16x16
        GRID_X = 12
        GRID_Y = 55
        CELL_W = 16
        CELL_H = 16
        
        # Calculate Pixel Center
        x = int(GRID_X + (col * CELL_W) + (CELL_W / 2))
        y = int(GRID_Y + (row * CELL_H) + (CELL_H / 2))
    
    print(f"-> Action: {button} at Row {row}, Col {col} -> Pixel ({x}, {y})")
    
    # Save debug image to verify click location
    # We need the last saved image path. It mimics the flow in main()
    # But perform_action doesn't know the image path easily unless passed.
    # Let's just re-open 'turn.png' which is the default from main loop
    save_debug_click_image("turn.png", x, y, f"debug_click_step_{int(time.time())}.png")
    
    payload = {
        "action_type": "mouse",
        "x": x,
        "y": y,
        "button": button,
        "mouse_state": "click"
    }
    
    try:
        requests.post(f"{API_URL}/step", json=payload)
    except Exception as e:
        print(f"API Error: {e}")
    
    return True, f"{x} {y} {button}"

def reset_game():
    # 1. Reset the game explicitly to fix "Stuck" state
    print("Resetting game environment...")
    try:
        requests.post(f"{API_URL}/reset")
        print("-> Game reset command sent. Waiting for app to launch...")
        time.sleep(5) # Wait for gnome-mines to reappear
        
        # 1.5 Click Smiley Face (New Game)
        # Smiley at 75, 55
        x, y = 75, 55
        print(f"-> Clicking New Game (Smiley) at ({x}, {y}) to reset...")
        
        requests.post(f"{API_URL}/step", json={
            "action_type": "mouse",
            "x": x,
            "y": y,
            "button": "left",
            "mouse_state": "click"
        })
        time.sleep(1)
        
    except Exception as e:
        print(f"Failed to reset/start game: {e}")


def main():
    print("Starting LLM Minesweeper Solver via OpenEnv API")
    print(f"Connecting to {API_URL}...")
    
    reset_game()
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use mock LLM response")
    args = parser.parse_args()
    
    step = 0
    previous_action = None
    previous_b64 = None
    
    while True:
        print(f"\n--- Step {step} ---")
        
        # 1. Capture
        b64 = get_screenshot()
        if not b64:
            print("Failed to capture screen.")
            time.sleep(2)
            continue
            
        img_path = save_image(b64)
        
        # 2. Analyze Change
        screen_changed = True
        if previous_b64 and b64 == previous_b64:
            screen_changed = False
            print("-> Detect: Screen did NOT change from last frame.")
        
        previous_b64 = b64
        
        # 3. Think (with feedback)
        if args.mock:
             print("[MOCK] Simulating LLM response...")
             # Alternate moves to show progress
             r, c = (step % 5) + 1, (step % 5) + 1
             response = f"Analysis: Mocking move for testing.\nMOVE: {r} {c} left"
             time.sleep(1)
        else:
             response = ask_claude(img_path, previous_action, screen_changed)
             
        print(f"LLM Response: {response}")
        
        # 4. Act
        success, action_desc = perform_action(response)
        
        if not success:
             if action_desc == "WON":
                 print("\n========== VICTORY! ==========")
                 print("The agent has WON the game!")
                 print("==============================")
                 break
             
             if action_desc == "LOST" or action_desc == "Forced Smiley Click":
                 print(f"\n!!! Game {action_desc} / Reset Triggered !!!")
                 reset_game()
                 step = 0
                 previous_action = None
                 previous_b64 = None
                 continue
             
             # Otherwise, it's a parse error or timeout. DO NOT RESET.
             print("\n[WARN] No valid move found or API error. Retrying... (Game NOT reset)")
             time.sleep(1)
             continue
        
        previous_action = action_desc
        
        step += 1
        time.sleep(1)

if __name__ == "__main__":
    main()
