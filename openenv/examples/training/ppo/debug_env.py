
import gymnasium
import stable_baselines3
import sys
import os

# Ensure we can import minesweeper_env
sys.path.append(os.getcwd())

try:
    from minesweeper_env import MinesweeperEnv
except ImportError as e:
    print(f"Failed to import MinesweeperEnv: {e}")
    sys.exit(1)

print(f"Gymnasium version: {gymnasium.__version__}")
print(f"SB3 version: {stable_baselines3.__version__}")

try:
    env = MinesweeperEnv()
    print(f"Env type: {type(env)}")
    print(f"Env bases: {type(env).__mro__}")
    print(f"Is instance of gymnasium.Env: {isinstance(env, gymnasium.Env)}")

    try:
        import gym
        print(f"Gym version: {gym.__version__}")
        print(f"Is instance of gym.Env: {isinstance(env, gym.Env)}")
    except ImportError:
        print("Gym (old) not installed")

    # define check_env
    from stable_baselines3.common.env_checker import check_env
    try:
        check_env(env)
        print("check_env passed")
    except Exception as e:
        print(f"check_env failed: {e}")

    from stable_baselines3.common.vec_env.dummy_vec_env import DummyVecEnv
    try:
        # Wrap the env properly
        venv = DummyVecEnv([lambda: MinesweeperEnv()])
        print("DummyVecEnv success")
    except Exception as e:
        print(f"DummyVecEnv failed: {e}")
        import traceback
        traceback.print_exc()

except Exception as e:
    print(f"Environment instantiation failed: {e}")
    import traceback
    traceback.print_exc()
