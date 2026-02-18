from minesweeper_env import MinesweeperEnv
import time
import numpy as np
import cv2
import os

def main():
    print("Testing MinesweeperEnv (No PPO)...")
    try:
        env = MinesweeperEnv(container_name="openenv")
    except Exception as e:
        print(f"Failed to init env: {e}")
        return

    print("Resetting Environment...")
    obs, info = env.reset()
    
    print("Observation Keys:", obs.keys())
    print("Screen Shape:", obs["screen"].shape)
    print("Memory Shape:", obs["memory"].shape)
    
    # Check if memory has data
    mem = obs["memory"]
    if np.all(mem == 0):
        print("WARNING: Memory observation is all zeros. Grid address may not have been found.")
    else:
        print("Memory Data Detected!")
        print("Sample (Top-Left 5x5):")
        print(mem[:5, :5])

    # Run loop
    print("\nRunning random actions...")
    for i in range(10):
        action = env.action_space.sample()
        obs, reward, done, truncated, info = env.step(action)
        
        print(f"Step {i}: Action={action}, Reward={reward}, Done={done}")
        
        # Save screenshot for debug
        # cv2.imwrite(f"debug_step_{i}.png", obs["screen"]) # Optional
        
        if done:
            print("Episode Finished!")
            env.reset()
            break
        
        time.sleep(0.5)

if __name__ == "__main__":
    main()
