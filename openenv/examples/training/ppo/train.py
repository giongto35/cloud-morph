import gymnasium as gym
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.vec_env import DummyVecEnv
from minesweeper_env import MinesweeperEnv
import os

def main():
    # Create logs directory
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Initialize Environment
    # We can pass container_name if it differs
    env = MinesweeperEnv(container_name="openenv")
    
    # Optional: Check if env follows Gym API
    # check_env(env) # Note: Might fail if API is offline or slow
    
    # Wrap in Vector Env
    env = DummyVecEnv([lambda: env])
    
    # PPO Model
    # We use MultiInputPolicy because observation is a Dict (screen + memory)
    # CnnPolicy feature extractor will facilitate the screen processing
    model = PPO(
        "MultiInputPolicy", 
        env, 
        verbose=1,
        # tensorboard_log=log_dir, # Disabled because tensorboard is not installed in container
        device="auto" # use GPU if available
    )
    
    print("Starting PPO Training...")
    # Train
    model.learn(total_timesteps=10000)
    
    # Save
    model.save("ppo_minesweeper")
    print("Training Complete. Model saved.")

if __name__ == "__main__":
    main()
