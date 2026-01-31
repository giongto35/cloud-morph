
import pyautogui
import time
import os

print("Testing Mouse Movement inside Container...")
print(f"DISPLAY={os.environ.get('DISPLAY')}")
print(f"Size: {pyautogui.size()}")

try:
    print("Moving to (100, 100)...")
    pyautogui.moveTo(100, 100)
    print(f"Current: {pyautogui.position()}")
    
    print("Moving to (400, 300)...")
    pyautogui.moveTo(400, 300)
    print(f"Current: {pyautogui.position()}")
    
    print("Clicking at (200, 220)...")
    pyautogui.moveTo(200, 220)
    pyautogui.mouseDown()
    time.sleep(0.5)
    pyautogui.mouseUp()
    print("Click done.")
    
except Exception as e:
    print(f"Error: {e}")
