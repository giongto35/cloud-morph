import requests
import time
import argparse

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
        else:
            print(f"Scan failed: {res.text}")
    except Exception as e:
        print(f"Error scanning: {e}")
    return []

def read(pid, address, size=4):
    try:
        payload = {
            "pid": pid,
            "address": address,
            "size": size
        }
        res = requests.post(f"{API_URL}/memory/read", json=payload)
        if res.status_code == 200:
            return res.json()
        else:
            print(f"Read failed: {res.text}")
    except Exception as e:
        print(f"Error reading: {e}")
    return None

def main():
    parser = argparse.ArgumentParser(description="Scan memory of a process via OpenEnv API")
    parser.add_argument("process", help="Name of the process (e.g., gnome-mines, wine)")
    args = parser.parse_args()
    
    print(f"Looking for process '{args.process}'...")
    pid = get_pid(args.process)
    
    if not pid:
        print(f"Process '{args.process}' not found.")
        return
        
    print(f"Found PID: {pid}")
    
    candidates = []
    first_scan = True
    
    while True:
        action = input("\n[S]can, [F]ilter, [R]ead, [Q]uit: ").lower()
        
        if action == 'q':
            break
            
        if action == 's':
            val_str = input("Enter value to scan for (int): ")
            try:
                val = int(val_str)
            except:
                print("Invalid integer")
                continue
                
            print("Scanning...")
            res = scan(pid, val)
            print(f"Found {len(res)} matches.")
            if len(res) < 100:
                print(f"Matches: {[hex(x) for x in res]}")
            candidates = res
            first_scan = False
            
        elif action == 'f':
            if first_scan:
                print("Scan first.")
                continue
                
            val_str = input("Enter NEW value to filter current candidates: ")
            try:
                val = int(val_str)
            except:
                print("Invalid integer")
                continue
                
            new_candidates = []
            print(f"Filtering {len(candidates)} candidates...")
            
            # This is naive: we re-read each candidate manually
            # A better API would be "scan_subset" but for now client-side filter is fine for small sets
            # For large sets, we should just re-scan globally and intersect sets
            
            # Let's use the global scan again and intersect, it's faster than reading 1 by 1 if list is huge
            current_matches = scan(pid, val)
            current_set = set(current_matches)
            
            candidates = [c for c in candidates if c in current_set]
            
            print(f"Remaining candidates: {len(candidates)}")
            if len(candidates) < 100:
                 print(f"Matches: {[hex(x) for x in candidates]}")
                 
        elif action == 'r':
            addr_str = input("Enter address (hex, e.g. 0x1234): ")
            try:
                addr = int(addr_str, 16)
            except:
                 print("Invalid hex address")
                 continue
                 
            data = read(pid, addr)
            if data:
                print(f"Data: {data.get('data_hex')} (Int: {int.from_bytes(bytes.fromhex(data.get('data_hex')), 'little')})")

if __name__ == "__main__":
    main()
