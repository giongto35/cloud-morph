import requests
import time
import sys
import struct

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
            return res.json()["addresses"]
    except Exception as e:
        print(f"Error scanning: {e}")
    return []

def set_expert_mode():
    print("Switching to Expert Mode (99 Mines)...")
    # Menu: Game (Alt+G) -> Expert (E)
    # OpenEnv xdotool supports sequences? 
    # Let's send them separately to be safe.
    requests.post(f"{API_URL}/step", json={"action_type": "key", "key": "alt+g"})
    time.sleep(0.5)
    requests.post(f"{API_URL}/step", json={"action_type": "key", "key": "e"})
    time.sleep(1)

def main():
    pid = get_pid("WineMine")
    if not pid:
        print("PID not found")
        sys.exit(1)
        
    set_expert_mode()
    
    # Check if we successfully switched by scanning for 99
    # Expert: Mines=99, Width=30, Height=16
    print("Scanning for Mines=99...")
    candidates = scan(pid, 99) # 4-byte int
    print(f"Found {len(candidates)} candidates for 99")
    
    for addr in candidates:
        # Check standard layout:
        # Addr = Mines (99)
        # Addr+4 = Width (30)
        # Addr+8 = Height (16)
        
        # Read 12 bytes
        res = requests.post(f"{API_URL}/memory/read", json={"pid": pid, "address": addr, "size": 12})
        if res.status_code != 200: continue
        
        data_hex = res.json()["data_hex"]
        data = bytes.fromhex(data_hex)
        
        try:
            mines = struct.unpack("I", data[0:4])[0]
            width = struct.unpack("I", data[4:8])[0]
            height = struct.unpack("I", data[8:12])[0]
            
            print(f"Candidate {hex(addr)}: M={mines}, W={width}, H={height}")
            
            if mines == 99 and width == 30 and height == 16:
                print(f"*** FOUND MATCH ***")
                print(f"  Mines Address: {hex(addr)}")
                print(f"  Width Address: {hex(addr+4)}")
                print(f"  Height Address: {hex(addr+8)}")
                print(f"  Grid (Offset +0x10): {hex(addr+16)}")
                
                # Double check Grid Border
                # Expert mode border is at Grid Start?
                # Read grid start
                res2 = requests.post(f"{API_URL}/memory/read", json={"pid": pid, "address": addr+16, "size": 32})
                print(f"  Grid Data Sample: {res2.json()['data_hex']}")
                sys.exit(0)
        except: pass

if __name__ == "__main__":
    main()
