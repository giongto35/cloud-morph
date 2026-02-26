#!/usr/bin/env python3
"""
Age of Empires II — Navigate menus to start a Single Player Random Map game.

Connects to the OpenEnv API and navigates AoE2's main menu to launch a
skirmish (Random Map) game against a computer opponent.

Menu path:
  Main Menu → Single Player → Random Map → [configure] → Start Game

Usage:
    python start_game.py               # navigate and start game
    python start_game.py --api http://host:8000
    python start_game.py --screenshot  # save screenshot after each step

NOTE: AoE2 classic takes ~15s to load before menus are visible.
      Run this after the game has fully started (check /viewer first).
"""

import requests
import time
import sys
import argparse
import base64

API_BASE = "http://localhost:8000"


def step(action: dict):
    try:
        r = requests.post(f"{API_BASE}/step", json=action, timeout=15)
        if r.status_code != 200:
            print(f"API Error: {r.status_code} - {r.text}")
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"Connection Error: {e}")
        sys.exit(1)


def click(x, y, delay=0.8):
    print(f"  Clicking ({x}, {y})...")
    step({"action_type": "mouse", "x": x, "y": y, "button": "left", "mouse_state": "click"})
    time.sleep(delay)


def key(k, delay=1.0):
    print(f"  Key: {k}")
    step({"action_type": "key", "key": k})
    time.sleep(delay)


def screenshot(name: str):
    """Capture screen and save to file."""
    try:
        obs = step({"action_type": "mouse", "x": 1, "y": 1, "mouse_state": "move"})
        if obs and obs.get("observation", {}).get("screen"):
            img_bytes = base64.b64decode(obs["observation"]["screen"])
            with open(name, "wb") as f:
                f.write(img_bytes)
            print(f"  Screenshot saved: {name}")
    except Exception as e:
        print(f"  Screenshot failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Navigate AoE2 menus to start a game")
    parser.add_argument("--api", default=API_BASE, help="OpenEnv API URL")
    parser.add_argument("--screenshot", action="store_true", help="Save screenshots after each step")
    parser.add_argument("--wait", type=float, default=15.0,
                        help="Seconds to wait for game to load (default: 15)")
    args = parser.parse_args()

    global API_BASE
    API_BASE = args.api

    # ── 1. Wait for game to load ──────────────────────────────────────────────
    print(f"Waiting {args.wait}s for Age of Empires II to load...")
    time.sleep(args.wait)

    if args.screenshot:
        screenshot("aoe2_00_loaded.jpg")

    # ── 2. Dismiss intro screen / copyright screen ────────────────────────────
    # AoE2 classic shows a splash screen; press Escape or click to dismiss
    print("\nStep 1: Dismiss intro splash screen...")
    key("Escape", delay=2.0)
    key("Escape", delay=2.0)

    if args.screenshot:
        screenshot("aoe2_01_main_menu.jpg")

    # ── 3. Main Menu → Single Player ─────────────────────────────────────────
    # Main menu layout (800x600):
    #   - Single Player button: ~(400, 280)
    #   - Multiplayer: ~(400, 320)
    #   - Options: ~(400, 360)
    #   - Exit: ~(400, 440)
    print("\nStep 2: Click 'Single Player'...")
    click(400, 280, delay=2.0)

    if args.screenshot:
        screenshot("aoe2_02_single_player.jpg")

    # ── 4. Single Player Menu → Random Map ───────────────────────────────────
    # Single Player sub-menu:
    #   - Random Map: ~(400, 270)
    #   - Regicide: ~(400, 310)
    #   - Death Match: ~(400, 350)
    #   - Scenario: ~(400, 390)
    #   - Campaign: ~(400, 430)
    print("\nStep 3: Click 'Random Map'...")
    click(400, 270, delay=2.0)

    if args.screenshot:
        screenshot("aoe2_03_random_map.jpg")

    # ── 5. Game Setup Screen ──────────────────────────────────────────────────
    # Random Map setup screen allows configuring players, map, difficulty.
    # The "Start Game" button is at the bottom right (~(670, 540))
    print("\nStep 4: Game setup screen - starting game with defaults...")
    time.sleep(1.0)

    # Optional: click difficulty or map settings here
    # click(400, 300, delay=1.0)  # Map type selection if needed

    # Click "Start Game"
    print("\nStep 5: Click 'Start Game'...")
    click(670, 540, delay=3.0)

    if args.screenshot:
        screenshot("aoe2_04_starting.jpg")

    # ── 6. Wait for map to load ───────────────────────────────────────────────
    print("\nWaiting for map to load (10s)...")
    time.sleep(10)

    if args.screenshot:
        screenshot("aoe2_05_ingame.jpg")

    print("\nDone! Game should be running.")
    print(f"Check the viewer at {API_BASE}/viewer")


if __name__ == "__main__":
    main()
