import sys
import struct

def get_maps(pid):
    maps = []
    try:
        with open(f"/proc/{pid}/maps", "r") as f:
            for line in f:
                parts = line.split()
                # format: 00400000-0040b000 r-xp ...
                addr_range = parts[0].split("-")
                start = int(addr_range[0], 16)
                end = int(addr_range[1], 16)
                perms = parts[1]
                if "r" in perms: # Only readable pages
                    maps.append((start, end))
    except Exception as e:
        pass
    return maps

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 local_memory_search.py <pid>")
        sys.exit(1)
        
    pid = sys.argv[1]
    
    best_addr = None
    best_score = 0.0
    
    try:
        with open(f"/proc/{pid}/mem", "rb", 0) as mem:
            maps = get_maps(pid)
            for start, end in maps:
                try:
                    size = end - start
                    if size > 10 * 1024 * 1024: continue 
                    
                    mem.seek(start)
                    data = mem.read(size)
                    
                    # Window: 256 bytes
                    for i in range(0, len(data) - 256, 128):
                        window = data[i:i+256]
                        count_0f = window.count(b'\x0f')
                        ratio_0f = count_0f / 256.0
                        
                        # Border check (0x10)
                        count_10 = window.count(b'\x10')
                        ratio_10 = count_10 / 256.0
                        
                        # Score: Prioritize 0x0F but boost if 0x10 is present (typical board)
                        score = ratio_0f + (ratio_10 * 0.5)
                        
                        if score > best_score and ratio_0f > 0.3:
                            best_score = score
                            best_addr = start + i
                                 
                except: pass
    except Exception as e:
        print(e)
        
    if best_addr:
        print(f"BEST_CANDIDATE: {hex(best_addr)}")
    else:
        print("BEST_CANDIDATE: None")

if __name__ == "__main__":
    main()
