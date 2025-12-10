#!/usr/bin/env python3
"""
Hello World Agent for OpenEnv Notepad
Types "helloworld" into the Notepad window via the OpenEnv API.
"""

import requests
import time
import argparse
from typing import List

# Key codes: A-Z = 65-90
KEY_CODES = {
    'a': 65, 'b': 66, 'c': 67, 'd': 68, 'e': 69, 'f': 70,
    'g': 71, 'h': 72, 'i': 73, 'j': 74, 'k': 75, 'l': 76,
    'm': 77, 'n': 78, 'o': 79, 'p': 80, 'q': 81, 'r': 82,
    's': 83, 't': 84, 'u': 85, 'v': 86, 'w': 87, 'x': 88,
    'y': 89, 'z': 90,
    ' ': 32,  # Space
}


class HelloWorldAgent:
    """Agent that types text into Notepad via OpenEnv API"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def reset(self) -> dict:
        """Reset the environment"""
        print("Resetting environment...")
        response = self.session.post(f"{self.base_url}/reset")
        response.raise_for_status()
        print("✓ Environment reset")
        return response.json()
    
    def step(self, key_code: int, key_state: str = "down") -> dict:
        """Send a key press"""
        action = {
            "action_type": "key",
            "key": key_code,
            "key_state": key_state
        }
        response = self.session.post(
            f"{self.base_url}/step",
            json={"action": action}
        )
        response.raise_for_status()
        return response.json()
    
    def type_text(self, text: str, delay: float = 0.1):
        """Type a string of text character by character"""
        print(f"Typing: '{text}'")
        
        for char in text:
            char_lower = char.lower()
            if char_lower not in KEY_CODES:
                print(f"Warning: Skipping unsupported character '{char}'")
                continue
            
            key_code = KEY_CODES[char_lower]
            
            # For uppercase letters, we'd need Shift, but for simplicity
            # we'll just type lowercase. The API handles key down/up automatically.
            print(f"  Pressing key: {char} (code: {key_code})")
            self.step(key_code, "down")
            time.sleep(delay)
        
        print("✓ Finished typing")
    
    def run(self, text: str = "helloworld", delay: float = 0.1):
        """Run the agent: reset environment and type text"""
        try:
            # Reset environment
            self.reset()
            time.sleep(0.5)  # Give Notepad time to focus
            
            # Type the text
            self.type_text(text, delay)
            
            print("\n✓ Agent completed successfully!")
            print(f"Check the viewer at: {self.base_url}/viewer")
            
        except requests.exceptions.RequestException as e:
            print(f"Error: Failed to connect to API at {self.base_url}")
            print(f"Make sure the OpenEnv container is running.")
            raise
        except Exception as e:
            print(f"Error: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(
        description="Hello World Agent for OpenEnv Notepad"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="OpenEnv API base URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--text",
        default="helloworld",
        help="Text to type (default: helloworld)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay between key presses in seconds (default: 0.1)"
    )
    
    args = parser.parse_args()
    
    agent = HelloWorldAgent(base_url=args.url)
    agent.run(text=args.text, delay=args.delay)


if __name__ == "__main__":
    main()

