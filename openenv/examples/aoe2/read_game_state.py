#!/usr/bin/env python3
"""
Age of Empires II (Classic 1.0c) — Memory-based Game State Reader

Reads player resources (food, wood, gold, stone), population, and age
directly from process memory via the OpenEnv `/memory/read` API.

Memory layout notes:
  AoE2 1.0c stores player data in a static structure. The offsets below
  are derived from community research and the AoE2 modding community.
  If values read as 0 or garbage, use the --scan mode to rediscover them.

  Player data base pointer: 0x006A2374 (player array)
  Each player struct is ~0x17E8 bytes apart.

Usage:
    python read_game_state.py                     # single read, print JSON
    python read_game_state.py --watch             # continuous polling
    python read_game_state.py --player 1          # read player 1 (default: 0)
    python read_game_state.py --scan 200          # scan for value 200 (e.g. starting food)
    python read_game_state.py --verify            # verify known addresses

NOTE: Values are for AoE2 1.0c running under Wine.
      The process must be findable via pgrep -f 'empires2'.
"""

import requests
import struct
import json
import time
import argparse
import sys

API_URL = "http://localhost:8000"

# ──────────────────────── AoE2 1.0c Memory Layout ────────────────────────
#
# AoE2 classic stores player resources in player data structures.
# Player data base is accessed via a pointer at a fixed address.
#
# These offsets are for AoE2 1.0c (empires2.exe, ~2.7MB version).
# Verify with --scan if the game version differs.
#
# Player struct array base pointer address:
PLAYER_DATA_PTR = 0x006A2374   # Points to array of player data pointers

# Offsets within each player's data struct (relative to player base ptr):
OFF_FOOD   = 0x0044   # float — current food
OFF_WOOD   = 0x0048   # float — current wood
OFF_STONE  = 0x004C   # float — current stone
OFF_GOLD   = 0x0050   # float — current gold
OFF_POP    = 0x00C4   # int32 — current population count
OFF_POP_CAP = 0x00C8  # int32 — population cap

# Alternatively, some versions use direct static addresses for player 0:
# These can be found by scanning for the starting resource values (200 food, etc.)
# Use --scan to discover the actual addresses for your version.

MAX_PLAYERS = 8  # AoE2 supports up to 8 players


# ──────────────────────── API Helpers ────────────────────────

def find_pid(process_name="empires2"):
    """Find the AoE2 process PID via the OpenEnv API."""
    try:
        r = requests.get(f"{API_URL}/process/{process_name}", timeout=5)
        if r.status_code == 200:
            return r.json()["pid"]
    except Exception as e:
        print(f"[!] Failed to find process '{process_name}': {e}", file=sys.stderr)
    return None


def read_mem(pid, address, size):
    """Read raw bytes from process memory via the OpenEnv API."""
    try:
        r = requests.post(f"{API_URL}/memory/read", json={
            "pid": pid,
            "address": address,
            "size": size,
        }, timeout=5)
        if r.status_code == 200:
            return bytes.fromhex(r.json()["data_hex"])
    except Exception as e:
        print(f"[!] memory/read error @ {hex(address)}: {e}", file=sys.stderr)
    return None


def read_u32(pid, address):
    """Read a single unsigned 32-bit int."""
    data = read_mem(pid, address, 4)
    if data and len(data) == 4:
        return struct.unpack("<I", data)[0]
    return None


def read_i32(pid, address):
    """Read a single signed 32-bit int."""
    data = read_mem(pid, address, 4)
    if data and len(data) == 4:
        return struct.unpack("<i", data)[0]
    return None


def read_float(pid, address):
    """Read a single 32-bit float."""
    data = read_mem(pid, address, 4)
    if data and len(data) == 4:
        return round(struct.unpack("<f", data)[0], 1)
    return None


def scan_for_value(pid, value, value_type="int"):
    """Use the /memory/scan API to find addresses holding a given value."""
    try:
        r = requests.post(f"{API_URL}/memory/scan", json={
            "pid": pid,
            "value": value,
            "value_type": value_type,
        }, timeout=60)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[!] scan error: {e}", file=sys.stderr)
    return None


# ──────────────────────── Player Data Reading ────────────────────────

def get_player_base(pid, player_index):
    """
    Resolve the base address for a player's data struct.
    AoE2 stores an array of player data pointers at PLAYER_DATA_PTR.
    player_index 0 = neutral/gaia, 1 = player 1, etc.
    """
    ptr_addr = PLAYER_DATA_PTR + player_index * 4
    player_base = read_u32(pid, ptr_addr)
    if player_base and player_base > 0x100000:  # sanity: must be a valid heap address
        return player_base
    return None


def read_player_resources(pid, player_base):
    """Read food/wood/gold/stone/pop from a player's data struct."""
    if not player_base:
        return None

    food  = read_float(pid, player_base + OFF_FOOD)
    wood  = read_float(pid, player_base + OFF_WOOD)
    stone = read_float(pid, player_base + OFF_STONE)
    gold  = read_float(pid, player_base + OFF_GOLD)
    pop   = read_i32(pid, player_base + OFF_POP)
    cap   = read_i32(pid, player_base + OFF_POP_CAP)

    return {
        "food": food,
        "wood": wood,
        "stone": stone,
        "gold": gold,
        "population": pop,
        "pop_cap": cap,
    }


def read_game_state(pid, player_ids=None):
    """
    Read game state for one or more players.

    Args:
        pid: Process ID of empires2.exe
        player_ids: list of player indices to read (default: [1] for player 1)

    Returns dict with player resources indexed by player_id.
    """
    if player_ids is None:
        player_ids = [1]

    state = {"players": {}}

    for pid_idx in player_ids:
        player_base = get_player_base(pid, pid_idx)
        if player_base:
            resources = read_player_resources(pid, player_base)
            state["players"][pid_idx] = resources or {}
            state["players"][pid_idx]["base_addr"] = hex(player_base)
        else:
            state["players"][pid_idx] = {"error": "could not resolve player base"}

    return state


# ──────────────────────── Verification Helper ────────────────────────

def verify_known_addresses(pid):
    """
    Verify that the known addresses are readable.
    Also prints the player data pointer values so you can verify they point
    to sane heap addresses.
    """
    print("=" * 60)
    print("AoE2 Memory Address Verification")
    print("=" * 60)
    print(f"PID: {pid}")
    print()

    print(f"--- Player Data Pointer Array (0x{PLAYER_DATA_PTR:08X}) ---")
    for i in range(MAX_PLAYERS + 1):  # 0 = gaia, 1-8 = players
        ptr_addr = PLAYER_DATA_PTR + i * 4
        base = read_u32(pid, ptr_addr)
        if base is not None:
            label = "gaia" if i == 0 else f"player {i}"
            print(f"  [{label}] ptr@0x{ptr_addr:08X} = 0x{base:08X}", end="")
            if base > 0x100000:
                # Try reading food from this base
                food = read_float(pid, base + OFF_FOOD)
                print(f"  food={food}", end="")
            print()
        else:
            print(f"  [player {i}] read failed")

    print()
    print("Tip: If base addresses are 0 or <0x100000, the game may not be")
    print("     in-game yet, or the offsets need updating for this version.")
    print("     Use --scan <value> to discover the correct addresses.")
    print()


# ──────────────────────── Main ────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Read Age of Empires II game state from memory via OpenEnv API"
    )
    parser.add_argument("--api", default=API_URL, help="OpenEnv API URL")
    parser.add_argument("--process", default="empires2",
                        help="Process name to search for (default: empires2)")
    parser.add_argument("--player", type=int, default=1,
                        help="Player index to read (1=player1, 2=player2, ...) (default: 1)")
    parser.add_argument("--all-players", action="store_true",
                        help="Read all player slots (0-8)")
    parser.add_argument("--watch", action="store_true",
                        help="Continuously poll and print state")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Poll interval in seconds (with --watch, default: 1.0)")
    parser.add_argument("--verify", action="store_true",
                        help="Verify known memory addresses are readable")
    parser.add_argument("--scan", type=int, default=None,
                        help="Scan memory for a specific integer value (e.g. 200 for starting food)")
    args = parser.parse_args()

    global API_URL
    API_URL = args.api

    # Find process
    pid = find_pid(args.process)
    if not pid:
        for name in ["empires2.exe", "empires2", "AoE2"]:
            pid = find_pid(name)
            if pid:
                break
    if not pid:
        print(f"[!] Could not find AoE2 process. Is the game running?", file=sys.stderr)
        sys.exit(1)

    print(f"Found AoE2 PID: {pid}", file=sys.stderr)

    # Verify mode
    if args.verify:
        verify_known_addresses(pid)
        return

    # Scan mode
    if args.scan is not None:
        print(f"Scanning for value {args.scan}...", file=sys.stderr)
        print("(This may take 30-60 seconds for a full memory scan)", file=sys.stderr)
        result = scan_for_value(pid, args.scan)
        if result:
            addrs = result.get("addresses", [])
            print(f"Found {len(addrs)} matches:", file=sys.stderr)
            print(json.dumps(result, indent=2))
        else:
            print("[!] Scan failed or returned no results")
        return

    # Determine which players to read
    player_ids = list(range(MAX_PLAYERS + 1)) if args.all_players else [args.player]

    # Read mode
    if args.watch:
        try:
            while True:
                state = read_game_state(pid, player_ids)
                print("\033[2J\033[H", end="")  # clear screen
                print(json.dumps(state, indent=2))
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.", file=sys.stderr)
    else:
        state = read_game_state(pid, player_ids)
        print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
