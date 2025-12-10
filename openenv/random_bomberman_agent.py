#!/usr/bin/env python3
"""
Drive Bomberman deterministically via OpenEnv API:
1) Start/Enter for 2 seconds
2) Move right with D for 4 seconds
3) Drop a bomb with numpad 3
4) Move left with A for 4 seconds

Usage:
  python random_bomberman_agent.py --base http://localhost:8000 --delay 0.1 --move-duration 4 --enter-duration 2
"""

import argparse
import time
from typing import Dict, Any

import requests


RIGHT_KEY = 68  # D
LEFT_KEY = 65   # A
BOMB_KEY = 34   # PAGE DOWN
ENTER_KEY = 13  # Enter/start


def send_key(session: requests.Session, base_url: str, key_code: int, label: str) -> None:
    action: Dict[str, Any] = {
        "action_type": "key",
        "key": key_code,
        "key_state": "down",
    }
    resp = session.post(f"{base_url}/step", json={"action": action}, timeout=5)
    resp.raise_for_status()
    print(f"Sent {label}: {action}")


def move_direction(session: requests.Session, base_url: str, key_code: int, label: str, duration: float, delay: float) -> None:
    """Press a direction key repeatedly for a duration."""
    repeats = max(1, int(duration / delay))
    print(f"Moving {label} for {duration:.2f}s ({repeats} presses every {delay:.2f}s)")
    for i in range(repeats):
        try:
            send_key(session, base_url, key_code, f"{label} [{i+1}/{repeats}]")
        except Exception as exc:
            print(f"Error sending {label} [{i+1}/{repeats}]: {exc}")
        time.sleep(delay)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000", help="OpenEnv base URL")
    parser.add_argument("--delay", type=float, default=0.1, help="Delay between key presses (seconds)")
    parser.add_argument("--move-duration", type=float, default=4.0, help="Seconds to move in each direction")
    parser.add_argument("--enter-duration", type=float, default=2.0, help="Seconds to press Enter before moving")
    args = parser.parse_args()

    s = requests.Session()

    # Reset environment
    print(f"Resetting environment at {args.base} ...")
    resp = s.post(f"{args.base}/reset", json={})
    resp.raise_for_status()
    print("Reset OK")

    move_direction(s, args.base, ENTER_KEY, "enter", args.enter_duration, args.delay)

    move_direction(s, args.base, RIGHT_KEY, "right (D)", args.move_duration, args.delay)

    # Drop bomb with numpad 3
    try:
        send_key(s, args.base, BOMB_KEY, "bomb (numpad 3)")
    except Exception as exc:
        print(f"Error sending bomb: {exc}")
    time.sleep(args.delay)

    move_direction(s, args.base, LEFT_KEY, "left (A)", args.move_duration, args.delay)

    print("Done.")


if __name__ == "__main__":
    main()

