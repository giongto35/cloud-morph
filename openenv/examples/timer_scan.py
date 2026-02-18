import requests
import time
import sys

API_URL = "http://localhost:8000"

def get_pid(process_name):
    try:
        res = requests.get(f"{API_URL}/process/{process_name}")
        if res.status_code == 200:
            return res.json()["pid"]
    except Exception as e:
        print(f"Error connecting to API: {e}")
    return None

def scan(pid, value, value_type="int"):
    try:
        payload = {
            "pid": pid,
            "value": value,
            "value_type": value_type
        }
        res = requests.post(f"{API_URL}/memory/scan", json=payload)
        if res.status_code == 200:
            return set(res.json()["addresses"])
    except Exception as e:
        print(f"Error scanning: {e}")
    return set()

def click_cell():
    print("Clicking cell to start timer...")
    # Cell (0,0) is approx at 20, 60? 
    # From solve_minesweeper.py: GRID_X0=12, GRID_Y0=55, CELL_SIZE=16. 
    # Center of 0,0 is 12 + 8 = 20, 55 + 8 = 63.
    action = {
        "action_type": "mouse",
        "x": 20,
        "y": 63,
        "button": "left",
        "mouse_state": "click"
    }
    requests.post(f"{API_URL}/step", json=action)

def reset_game():
    print("Resetting game (F2)...")
    requests.post(f"{API_URL}/step", json={"action_type": "key", "key": "F2"})
    time.sleep(1)

def main():
    pid = get_pid("WineMine")
    if not pid:
        print("PID not found")
        sys.exit(1)
        
    # 1. Reset Game -> Timer = 0
    reset_game()
    print("Phase 1: Scanning for 0...")
    candidates_0 = scan(pid, 0)
    print(f"  Found {len(candidates_0)} candidates")
    
    # 2. Start Game by clicking
    click_cell()
    print("Waiting 3 seconds for timer to tick...")
    time.sleep(3)
    
    # 3. Scan for 3 (or 2 or 4)
    print("Phase 2: Scanning for 3...")
    candidates_3 = scan(pid, 3)
    print(f"  Found {len(candidates_3)} candidates")
    
    # 4. Intersection
    # The address in candidates_3 must be in candidates_0
    intersection = candidates_0.intersection(candidates_3)
    print(f"Found {len(intersection)} Intersection candidates: {[hex(x) for x in intersection]}")
    
    if len(intersection) > 0:
        timer_addr = list(intersection)[0]
        print(f"*** TIMER ADDRESS LIKELY: {hex(timer_addr)} ***")
        
        # Verify specific standard offsets from Timer
        # XP Minesweeper:
        # Timer:  0x100579c
        # Mines:  0x1005330 (-0x46C from Timer)
        # Width:  0x1005334 (-0x468)
        # Height: 0x1005338 (-0x464)
        
        # Check relative values
        mines_addr = timer_addr - 0x46C
        width_addr = timer_addr - 0x468
        height_addr = timer_addr - 0x464
        
        print(f"Checking inferred addresses:")
        print(f"  Mines @ {hex(mines_addr)}")
        print(f"  Width @ {hex(width_addr)}")
        print(f"  Height @ {hex(height_addr)}")
        
        # Read them
        try:
            mines_val = requests.post(f"{API_URL}/memory/read", json={"pid": pid, "address": mines_addr, "size": 4}).json()['data_hex']
            width_val = requests.post(f"{API_URL}/memory/read", json={"pid": pid, "address": width_addr, "size": 4}).json()['data_hex']
            height_val = requests.post(f"{API_URL}/memory/read", json={"pid": pid, "address": height_addr, "size": 4}).json()['data_hex']
            
            import struct
            m = struct.unpack('<I', bytes.fromhex(mines_val))[0]
            w = struct.unpack('<I', bytes.fromhex(width_val))[0]
            h = struct.unpack('<I', bytes.fromhex(height_val))[0]
            
            print(f"  Values -> Mines: {m}, Width: {w}, Height: {h}")
            
            if m == 10 and w == 9 and h == 9:
                print("  *** CONFIRMED STRUCTURE MATCH ***")
        except Exception as e:
            print(f"Error verification: {e}")

if __name__ == "__main__":
    main()
