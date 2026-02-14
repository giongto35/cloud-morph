
import subprocess
import time
import os
import re

print("Testing Mouse Movement inside Container (xdotool)...")
print(f"DISPLAY={os.environ.get('DISPLAY')}")

def run_xdo(*args):
    cmd = ['xdotool'] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

def get_position():
    out = run_xdo('getmouselocation')
    # Output format: x:100 y:100 screen:0 window:12345
    m = re.search(r'x:(\d+)\s+y:(\d+)', out)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None

try:
    print("Moving to (100, 100)...")
    run_xdo('mousemove', '100', '100')
    print(f"Current: {get_position()}")
    
    print("Moving to (400, 300)...")
    run_xdo('mousemove', '400', '300')
    print(f"Current: {get_position()}")
    
    print("Clicking at (200, 220)...")
    run_xdo('mousemove', '200', '220')
    run_xdo('mousedown', '1')
    time.sleep(0.5)
    run_xdo('mouseup', '1')
    print("Click done.")
    
except Exception as e:
    print(f"Error: {e}")
