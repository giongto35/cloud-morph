#!/usr/bin/env python3
"""
Send random actions to the Bomberman OpenEnv API.

Usage:
  python random_bomberman_agent.py --base http://localhost:8000 --steps 200 --delay 0.2
"""

import argparse
import random
import time
from typing import Dict, Any

import requests


# Allowed Bomberman controls: arrows + Enter only
ARROW_KEYS = [37, 38, 39, 40]  # left, up, right, down
ENTER_KEY = 13                 # enter/start


def random_action() -> Dict[str, Any]:
    """Sample a random key action (arrows + enter)."""
    key_code = random.choice(ARROW_KEYS + [ENTER_KEY])
    return {
        "action_type": "key",
        "key": key_code,
        "key_state": "down",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000", help="OpenEnv base URL")
    parser.add_argument("--steps", type=int, default=200, help="Number of random actions to send")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between actions (seconds)")
    args = parser.parse_args()

    s = requests.Session()

    # Reset environment
    print(f"Resetting environment at {args.base} ...")
    resp = s.post(f"{args.base}/reset", json={})
    resp.raise_for_status()
    print("Reset OK")

    for i in range(args.steps):
        action = random_action()
        try:
            resp = s.post(f"{args.base}/step", json={"action": action}, timeout=5)
            resp.raise_for_status()
            print(f"[{i+1}/{args.steps}] sent action: {action}")
        except Exception as exc:
            print(f"[{i+1}] error sending action: {exc}")
        time.sleep(args.delay)

    print("Done.")


if __name__ == "__main__":
    main()

