#!/usr/bin/env python3
"""
StarCraft: Brood War — Memory-based Game State Reader

Reads game state (minerals, gas, supply, unit counts, frame count, etc.)
directly from process memory via the OpenEnv `/memory/read` API.

Memory layout is derived from BWAPI's BWGame struct (v1.16.1):
  https://github.com/bwapi/bwapi/blob/master/bwapi/BWAPI/Source/BW/BWGame.h

BWGame base address: 0x0057F0F0
All offsets below are relative to this base.

Usage:
    python read_game_state.py                  # single read, print JSON
    python read_game_state.py --watch          # continuous polling
    python read_game_state.py --watch --raw    # include hex dump of supply block

NOTE: Values are for StarCraft: Brood War 1.16.1 running under Wine.
      The process must be findable via pgrep -f 'StarCraft'.
"""

import requests
import struct
import json
import time
import argparse
import sys

API_URL = "http://localhost:8000"

# ──────────────────────── BWAPI BWGame Struct Layout ────────────────────────
# Base address of BWGame in StarCraft 1.16.1
BWGAME_BASE = 0x0057F0F0

PLAYER_COUNT = 12  # SC supports up to 12 player slots
RACE_COUNT = 3     # Zerg=0, Terran=1, Protoss=2
RACE_NAMES = ["Zerg", "Terran", "Protoss"]

# Offsets within BWGame (from BWAPI OFFSET_ASSERT)
OFF_MINERALS          = 0x00    # s32[12]  — current minerals per player
OFF_GAS               = 0x30    # s32[12]  — current gas per player
OFF_CUMULATIVE_GAS    = 0x60    # s32[12]
OFF_CUMULATIVE_MINERALS = 0x90  # s32[12]
OFF_SLOT_TYPES        = 0xC4    # u8[12]   — slot type (0=inactive, 2=human, etc.)
OFF_SLOT_RACES        = 0xD0    # u8[12]   — 0=Zerg, 1=Terran, 2=Protoss, 5=Random, ...
OFF_MAP_TILE_SIZE     = 0xE4    # u16[2]   — map width, height in tiles
OFF_FRAME_COUNT       = 0x14C   # u32      — game frame counter
OFF_ELAPSED_SECONDS   = 0x150   # u32      — saved elapsed game seconds

# Score / unit stat arrays (s32[12] each)
OFF_ALL_UNITS_TOTAL      = 0x2CF4
OFF_ALL_UNITS_PRODUCED   = 0x2D24
OFF_ALL_UNITS_OWNED      = 0x2D54
OFF_ALL_UNITS_LOST       = 0x2D84
OFF_ALL_UNITS_KILLED     = 0x2DB4
OFF_ALL_BUILDINGS_OWNED  = 0x2EA4
OFF_ALL_BUILDINGS_LOST   = 0x2ED4

# Supply block at offset 0x3054
# struct SuppliesPerRace { s32[12] available; s32[12] used; s32[12] max; }
# std::array<SuppliesPerRace, 3> supplies;   (indexed by race: Zerg=0 Terran=1 Protoss=2)
OFF_SUPPLIES = 0x3054
SUPPLY_PER_RACE_SIZE = PLAYER_COUNT * 4 * 3  # 3 arrays of 12 s32 = 144 bytes
SUPPLIES_TOTAL_SIZE  = SUPPLY_PER_RACE_SIZE * RACE_COUNT  # 432 bytes

# PlayerSlotTypes interpretation
SLOT_TYPE_NAMES = {
    0: "Inactive",
    1: "Computer",
    2: "Human",
    3: "RescuePassive",
    5: "Computer(SlotOpen)",
    6: "Open",
    7: "Neutral",
    8: "Closed",
}


# ──────────────────────── API Helpers ────────────────────────

def find_pid(process_name="StarCraft"):
    """Find the StarCraft process PID via the OpenEnv API."""
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


def read_s32_array(pid, base_offset, count=PLAYER_COUNT):
    """Read an array of signed 32-bit ints from BWGame + offset."""
    addr = BWGAME_BASE + base_offset
    data = read_mem(pid, addr, count * 4)
    if data and len(data) == count * 4:
        return list(struct.unpack(f"<{count}i", data))
    return None


def read_u8_array(pid, base_offset, count=PLAYER_COUNT):
    """Read an array of unsigned bytes from BWGame + offset."""
    addr = BWGAME_BASE + base_offset
    data = read_mem(pid, addr, count)
    if data and len(data) == count:
        return list(data)
    return None


def read_u32(pid, base_offset):
    """Read a single unsigned 32-bit int."""
    addr = BWGAME_BASE + base_offset
    data = read_mem(pid, addr, 4)
    if data and len(data) == 4:
        return struct.unpack("<I", data)[0]
    return None


def read_u16_pair(pid, base_offset):
    """Read two unsigned 16-bit ints (e.g. map size)."""
    addr = BWGAME_BASE + base_offset
    data = read_mem(pid, addr, 4)
    if data and len(data) == 4:
        return struct.unpack("<HH", data)
    return None


# ──────────────────────── Game State Extraction ────────────────────────

def read_game_state(pid):
    """
    Read game state from StarCraft memory and return a JSON-serializable dict.
    
    Returns dict with:
        - frame_count, elapsed_seconds
        - map_size (tiles)
        - players[] with minerals, gas, supply_used, supply_available, supply_max,
          race, slot_type, units_owned, buildings_owned, etc.
    """
    state = {}

    # Frame count & time
    state["frame_count"] = read_u32(pid, OFF_FRAME_COUNT)
    state["elapsed_seconds"] = read_u32(pid, OFF_ELAPSED_SECONDS)

    # Map size
    map_size = read_u16_pair(pid, OFF_MAP_TILE_SIZE)
    if map_size:
        state["map_size"] = {"width": map_size[0], "height": map_size[1]}

    # Player-level data
    minerals      = read_s32_array(pid, OFF_MINERALS)
    gas           = read_s32_array(pid, OFF_GAS)
    cum_minerals  = read_s32_array(pid, OFF_CUMULATIVE_MINERALS)
    cum_gas       = read_s32_array(pid, OFF_CUMULATIVE_GAS)
    slot_types    = read_u8_array(pid, OFF_SLOT_TYPES)
    slot_races    = read_u8_array(pid, OFF_SLOT_RACES)

    units_owned      = read_s32_array(pid, OFF_ALL_UNITS_OWNED)
    units_killed     = read_s32_array(pid, OFF_ALL_UNITS_KILLED)
    units_lost       = read_s32_array(pid, OFF_ALL_UNITS_LOST)
    units_produced   = read_s32_array(pid, OFF_ALL_UNITS_PRODUCED)
    buildings_owned  = read_s32_array(pid, OFF_ALL_BUILDINGS_OWNED)
    buildings_lost   = read_s32_array(pid, OFF_ALL_BUILDINGS_LOST)

    # Supply: read entire block and parse per-race
    supply_data = read_mem(pid, BWGAME_BASE + OFF_SUPPLIES, SUPPLIES_TOTAL_SIZE)

    players = []
    for i in range(PLAYER_COUNT):
        slot = slot_types[i] if slot_types else 0
        # Skip inactive/closed slots for cleaner output
        if slot in (0, 8):
            continue

        race_id = slot_races[i] if slot_races else 0
        race_name = RACE_NAMES[race_id] if race_id < len(RACE_NAMES) else f"Unknown({race_id})"

        # Determine supply for this player's race
        supply_used = 0
        supply_available = 0
        supply_max = 0
        if supply_data and race_id < RACE_COUNT:
            # SuppliesPerRace layout: available[12] + used[12] + max[12] = 144 bytes
            race_offset = race_id * SUPPLY_PER_RACE_SIZE
            avail_arr = struct.unpack_from(f"<{PLAYER_COUNT}i", supply_data, race_offset)
            used_arr  = struct.unpack_from(f"<{PLAYER_COUNT}i", supply_data, race_offset + PLAYER_COUNT * 4)
            max_arr   = struct.unpack_from(f"<{PLAYER_COUNT}i", supply_data, race_offset + PLAYER_COUNT * 4 * 2)
            # BW stores supply as 2× the displayed value (1 marine = 2 supply internally)
            supply_available = avail_arr[i] // 2
            supply_used = used_arr[i] // 2
            supply_max = max_arr[i] // 2

        player = {
            "id": i,
            "slot_type": SLOT_TYPE_NAMES.get(slot, f"Unknown({slot})"),
            "race": race_name,
            "minerals": minerals[i] if minerals else 0,
            "gas": gas[i] if gas else 0,
            "supply_used": supply_used,
            "supply_available": supply_available,
            "supply_max": supply_max,
            "cumulative_minerals": cum_minerals[i] if cum_minerals else 0,
            "cumulative_gas": cum_gas[i] if cum_gas else 0,
            "units_owned": units_owned[i] if units_owned else 0,
            "units_produced": units_produced[i] if units_produced else 0,
            "units_killed": units_killed[i] if units_killed else 0,
            "units_lost": units_lost[i] if units_lost else 0,
            "buildings_owned": buildings_owned[i] if buildings_owned else 0,
            "buildings_lost": buildings_lost[i] if buildings_lost else 0,
        }
        players.append(player)

    state["players"] = players
    return state


def read_game_state_minimal(pid, player_id=0):
    """
    Minimal read — just the essentials for a single player.
    Good for fast polling during RL training.

    Returns:
        {
            "frame": int,
            "minerals": int,
            "gas": int,
            "supply_used": int,
            "supply_available": int,
            "units_owned": int,
            "buildings_owned": int,
            "units_killed": int,
            "units_lost": int,
        }
    """
    result = {}

    # Frame
    result["frame"] = read_u32(pid, OFF_FRAME_COUNT) or 0

    # Read minerals and gas for this player (just 4 bytes each at the right offset)
    addr_min = BWGAME_BASE + OFF_MINERALS + player_id * 4
    addr_gas = BWGAME_BASE + OFF_GAS + player_id * 4
    data_min = read_mem(pid, addr_min, 4)
    data_gas = read_mem(pid, addr_gas, 4)
    result["minerals"] = struct.unpack("<i", data_min)[0] if data_min else 0
    result["gas"] = struct.unpack("<i", data_gas)[0] if data_gas else 0

    # Read supply for this player — need to know their race first
    races = read_u8_array(pid, OFF_SLOT_RACES)
    race_id = races[player_id] if races and player_id < len(races) else 1
    if race_id < RACE_COUNT:
        supply_base = BWGAME_BASE + OFF_SUPPLIES + race_id * SUPPLY_PER_RACE_SIZE
        # available, used, max — read just the one player's slot
        avail = read_mem(pid, supply_base + player_id * 4, 4)
        used  = read_mem(pid, supply_base + PLAYER_COUNT * 4 + player_id * 4, 4)
        result["supply_available"] = struct.unpack("<i", avail)[0] // 2 if avail else 0
        result["supply_used"] = struct.unpack("<i", used)[0] // 2 if used else 0
    else:
        result["supply_available"] = 0
        result["supply_used"] = 0

    # Unit stats — single player slot
    for name, offset in [
        ("units_owned", OFF_ALL_UNITS_OWNED),
        ("buildings_owned", OFF_ALL_BUILDINGS_OWNED),
        ("units_killed", OFF_ALL_UNITS_KILLED),
        ("units_lost", OFF_ALL_UNITS_LOST),
    ]:
        addr = BWGAME_BASE + offset + player_id * 4
        d = read_mem(pid, addr, 4)
        result[name] = struct.unpack("<i", d)[0] if d else 0

    return result


# ──────────────────────── Memory Scanning Helpers ────────────────────────

def scan_for_value(pid, value, value_type="int"):
    """Use the /memory/scan API to find addresses holding a given value."""
    try:
        r = requests.post(f"{API_URL}/memory/scan", json={
            "pid": pid,
            "value": value,
            "value_type": value_type,
        }, timeout=30)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[!] scan error: {e}", file=sys.stderr)
    return None


def verify_known_addresses(pid):
    """
    Verify that the known BWAPI addresses work by reading and displaying them.
    Useful for confirming the offsets match your StarCraft version.
    """
    print("=" * 60)
    print("StarCraft Memory Address Verification")
    print("=" * 60)

    # Try multiple process names
    if pid is None:
        for name in ["StarCraft", "StarCraft.exe", "starcraft"]:
            pid = find_pid(name)
            if pid:
                break

    if not pid:
        print("[!] Could not find StarCraft process!")
        return

    print(f"PID: {pid}")
    print()

    # Minerals
    print(f"--- Minerals (base 0x{BWGAME_BASE + OFF_MINERALS:08X}) ---")
    minerals = read_s32_array(pid, OFF_MINERALS)
    if minerals:
        for i, v in enumerate(minerals):
            if v != 0:
                print(f"  Player {i}: {v}")
    else:
        print("  [Failed to read]")

    # Gas
    print(f"\n--- Gas (base 0x{BWGAME_BASE + OFF_GAS:08X}) ---")
    gas = read_s32_array(pid, OFF_GAS)
    if gas:
        for i, v in enumerate(gas):
            if v != 0:
                print(f"  Player {i}: {v}")
    else:
        print("  [Failed to read]")

    # Frame count
    print(f"\n--- Frame Count (0x{BWGAME_BASE + OFF_FRAME_COUNT:08X}) ---")
    fc = read_u32(pid, OFF_FRAME_COUNT)
    print(f"  Frame: {fc}")

    # Supply
    print(f"\n--- Supply (base 0x{BWGAME_BASE + OFF_SUPPLIES:08X}) ---")
    slot_races = read_u8_array(pid, OFF_SLOT_RACES)
    slot_types = read_u8_array(pid, OFF_SLOT_TYPES)
    supply_data = read_mem(pid, BWGAME_BASE + OFF_SUPPLIES, SUPPLIES_TOTAL_SIZE)
    if supply_data and slot_races and slot_types:
        for i in range(PLAYER_COUNT):
            if slot_types[i] in (0, 8):
                continue
            race_id = slot_races[i]
            if race_id >= RACE_COUNT:
                continue
            race_offset = race_id * SUPPLY_PER_RACE_SIZE
            avail_arr = struct.unpack_from(f"<{PLAYER_COUNT}i", supply_data, race_offset)
            used_arr  = struct.unpack_from(f"<{PLAYER_COUNT}i", supply_data, race_offset + PLAYER_COUNT * 4)
            max_arr   = struct.unpack_from(f"<{PLAYER_COUNT}i", supply_data, race_offset + PLAYER_COUNT * 4 * 2)
            print(f"  Player {i} ({RACE_NAMES[race_id]}): "
                  f"{used_arr[i]//2}/{avail_arr[i]//2} (max {max_arr[i]//2})")
    else:
        print("  [Failed to read]")

    print()


# ──────────────────────── Main ────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Read StarCraft: Brood War game state from memory via OpenEnv API"
    )
    parser.add_argument("--api", default=API_URL, help="OpenEnv API URL")
    parser.add_argument("--process", default="StarCraft",
                        help="Process name to search for")
    parser.add_argument("--player", type=int, default=0,
                        help="Player ID for minimal mode (default: 0)")
    parser.add_argument("--watch", action="store_true",
                        help="Continuously poll and print state")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Poll interval in seconds (with --watch)")
    parser.add_argument("--minimal", action="store_true",
                        help="Read minimal state (faster, single player)")
    parser.add_argument("--verify", action="store_true",
                        help="Verify known memory addresses are readable")
    parser.add_argument("--scan", type=int, default=None,
                        help="Scan memory for a specific integer value")
    args = parser.parse_args()

    global API_URL
    API_URL = args.api

    # Find process
    pid = find_pid(args.process)
    if not pid:
        # Try common variants
        for name in ["StarCraft.exe", "starcraft", "StarCraft"]:
            pid = find_pid(name)
            if pid:
                break
    if not pid:
        print(f"[!] Could not find process. Is StarCraft running?", file=sys.stderr)
        sys.exit(1)

    print(f"Found StarCraft PID: {pid}", file=sys.stderr)

    # Verify mode
    if args.verify:
        verify_known_addresses(pid)
        return

    # Scan mode
    if args.scan is not None:
        print(f"Scanning for value {args.scan}...", file=sys.stderr)
        result = scan_for_value(pid, args.scan)
        print(json.dumps(result, indent=2))
        return

    # Read mode
    if args.watch:
        try:
            while True:
                if args.minimal:
                    state = read_game_state_minimal(pid, args.player)
                else:
                    state = read_game_state(pid)
                # Clear screen and print
                print("\033[2J\033[H", end="")
                print(json.dumps(state, indent=2))
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.", file=sys.stderr)
    else:
        if args.minimal:
            state = read_game_state_minimal(pid, args.player)
        else:
            state = read_game_state(pid)
        print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
