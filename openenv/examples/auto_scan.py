import requests
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
        else:
            print(f"Scan failed: {res.text}")
    except Exception as e:
        print(f"Error scanning: {e}")
    return []

def main():
    print("Auto-scanning for Minesweeper variables...")
    pid = get_pid("WineMine")
    if not pid:
        print("WineMine not found")
        sys.exit(1)
        
    print(f"PID: {pid}")
    
    
    # Strategy 3: Search for Mine Count (10) 
    # This is a 4-byte integer.
    # If we find 10, check +4 for Width(9) and +8 for Height(9)
    print("Scanning for Mine Count (10)...")
    val = 10 
    
    candidates = scan(pid, val, "int")
    print(f"Found {len(candidates)} candidates for 10")
    
    for i, addr in enumerate(candidates):
        # Read a chunk around this address to visualize structure
        # We try to find the header: Mines(10), Width(9), Height(9)
        # located closely before the grid data.
        
        # Read 640 bytes chunk centered roughly on the match, biased towards start
        # Match is at 'addr'. Assume match is start of grid or near it.
        # Header should be ~12-32 bytes before.
        
        start_read = addr - 64
        size_read = 256
        
        res = requests.post(f"{API_URL}/memory/read", json={"pid": pid, "address": start_read, "size": size_read})
        if res.status_code != 200: continue
        
        data_hex = res.json()["data_hex"]
        data = bytes.fromhex(data_hex)
        
        # 1. Try to find the standard header pattern
        # [Mines][Width][Height]
        found_header = False
        for offset in range(0, len(data) - 16, 1): # Scan byte by byte
            try:
                mines = struct.unpack("I", data[offset:offset+4])[0]
                width = struct.unpack("I", data[offset+4:offset+8])[0]
                height = struct.unpack("I", data[offset+8:offset+12])[0]
                
                if mines == 10 and width == 9 and height == 9:
                     base_addr = start_read + offset
                     print(f"  *** HEADER MATCH FOUND ***")
                     print(f"  Matched at local offset {offset} (Global: {hex(base_addr)})")
                     print(f"    Mines Addr: {hex(base_addr)}")
                     print(f"    Width Addr: {hex(base_addr+4)}")
                     print(f"    Height Addr: {hex(base_addr+8)}")
                     print(f"    Grid likely starts at: {hex(base_addr+12)}")
                     
                     # Dump grid start
                     grid_offset = offset + 12
                     print(f"    Grid Data: {data[grid_offset:grid_offset+32].hex()}")
                     found_header = True
                     # We might want to stop, or find all matches
                     # For now, let's stop on first strong match
                     sys.exit(0)
            except: pass
            
        # 2. Debug Dump for first few candidates if no header found
        if i < 5:
            print(f"  DEBUG: Candidate {hex(addr)} (No Header match). Dumping -64 to +128 rel to match:")
            # 'addr' is at offset 64. 
            start_off = 0
            end_off = 192
            
            # Print in lines of 32 bytes
            for j in range(start_read, start_read + size_read, 32):
                chunk = data[j-start_read : j-start_read+32]
                print(f"    {hex(j)}: {chunk.hex()}")
                
            # Heuristic: Check for 0x0F (Hidden) or 0x40 (Empty) nearby
            count_hidden = data.count(b'\x0f')
            count_empty = data.count(b'\x40')
            print(f"    Stats in this block: 0x0F={count_hidden}, 0x40={count_empty}")
            
            if count_hidden > 5:
                print("    POTENTIAL GRID DETECTED due to high 0x0F count!")


if __name__ == "__main__":
    main()
