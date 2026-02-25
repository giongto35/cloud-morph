#!/usr/bin/env python3
"""
StarCraft Brood War - Start Custom Melee Game.
Connects to OpenEnv API and navigates menus to start a 1v1 custom game.

Path: Main Menu → Single Player → Expansion → Profile Select →
      Episode Select → Play Custom → AIIDE folder → select map → Ok

NOTE: Requires xdotool mousemove --sync fix in wine_environment.py
for reliable mouse clicks.
"""

import requests
import time
import sys

API_BASE = "http://localhost:8000"


def step(action: dict):
    try:
        r = requests.post(f"{API_BASE}/step", json=action, timeout=15)
        if r.status_code != 200:
            print(f"API Error: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Connection Error: {e}")
        sys.exit(1)


def click(x, y):
    print(f"Clicking at ({x}, {y})...")
    step({"action_type": "mouse", "x": x, "y": y, "button": "left", "mouse_state": "click"})
    time.sleep(0.5)


def main():
    print("Waiting for StarCraft to settle (8s)...")
    time.sleep(8)

    print("Sending 's' for Single Player...")
    step({"action_type": "key", "key": "s"})
    time.sleep(2)

    print("Sending 'e' for Expansion...")
    step({"action_type": "key", "key": "e"})
    time.sleep(2)

    # Profile/Registry selection — press Return to select default profile
    print("Sending 'Return' to select profile...")
    step({"action_type": "key", "key": "Return"})
    time.sleep(3)

    # Episode selection screen (Terran V / Protoss IV / Zerg VI)
    # Click "Play Custom" button at (340, 420)
    print("Clicking 'Play Custom' (340, 420)...")
    click(340, 420)
    time.sleep(2)

    # Create game file browser — in BroodWar folder
    # Click AIIDE folder and press Return to enter it
    print("Selecting AIIDE folder (100, 140)...")
    click(100, 140)
    time.sleep(0.5)
    step({"action_type": "key", "key": "Return"})
    time.sleep(2)

    # (2)Benzene.scx is auto-selected (first map, 2 players)
    # Click Ok to start the game
    print("Clicking 'Ok' to start game (540, 395)...")
    click(540, 395)
    time.sleep(8)

    # Dismiss "Starcraft Tips" dialog
    print("Dismissing tips dialog (Return)...")
    step({"action_type": "key", "key": "Return"})

    print("Done! Game should be running. Check the viewer.")


if __name__ == "__main__":
    main()
