#!/usr/bin/env python3
"""Rollout worker for distributed PPO training.

Runs inside a Kubernetes pod alongside an OpenEnv sidecar container.
- Waits for OpenEnv to become healthy
- Navigates StarCraft menus to start a game
- Loads model.pt from shared PVC
- Collects ROLLOUT_STEPS transitions
- Computes GAE advantages
- Saves rollout as .npz + .done marker to PVC
"""

import os
import sys
import time

import numpy as np
import requests
import torch

from openenv_gym import OpenEnvGym, ALL_ACTIONS
from reward import MemoryRewardWrapper
from ppo import CNNAgent, compute_gae

# Configuration from environment
WORKER_ID = int(os.environ.get("WORKER_ID", "0"))
ITERATION = int(os.environ.get("ITERATION", "0"))
ROLLOUT_STEPS = int(os.environ.get("ROLLOUT_STEPS", "128"))
OPENENV_URL = os.environ.get("OPENENV_URL", "http://localhost:8000")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
NUM_ACTIONS = int(os.environ.get("NUM_ACTIONS", "35"))
GAMMA = float(os.environ.get("GAMMA", "0.99"))
GAE_LAMBDA = float(os.environ.get("GAE_LAMBDA", "0.95"))


def wait_for_openenv(url, timeout=300):
    """Wait for OpenEnv sidecar to become healthy."""
    print(f"Waiting for OpenEnv at {url} ...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{url}/health", timeout=3)
            if r.status_code == 200:
                print("OpenEnv is healthy!")
                return True
        except Exception:
            pass
        time.sleep(2)
    print("ERROR: OpenEnv did not become healthy in time.")
    return False


def navigate_starcraft_menus(url):
    """Navigate StarCraft main menu to start a single player game."""
    print("Navigating StarCraft menus...")

    def step(action):
        try:
            requests.post(f"{url}/step", json=action, timeout=5)
        except Exception as e:
            print(f"Menu nav error: {e}")

    # Wait for game to load
    time.sleep(8)

    # Single Player
    step({"action_type": "key", "key": "s"})
    time.sleep(2)

    # Expansion
    step({"action_type": "key", "key": "e"})
    time.sleep(2)

    # Select profile
    step({"action_type": "key", "key": "Return"})
    time.sleep(2)

    # Enter lobby
    step({"action_type": "key", "key": "Return"})
    time.sleep(3)

    # Select race
    step({"action_type": "key", "key": "Down"})
    time.sleep(0.5)

    # Click OK / Start game
    step({
        "action_type": "mouse", "x": 560, "y": 440,
        "button": "left", "mouse_state": "click",
    })
    time.sleep(1)

    step({"action_type": "key", "key": "Return"})
    time.sleep(1)
    step({"action_type": "key", "key": "Return"})
    time.sleep(3)

    print("Menu navigation complete.")


def load_model(iteration, num_actions):
    """Load model from PVC."""
    model_path = os.path.join(DATA_DIR, "model.pt")
    agent = CNNAgent(num_actions=num_actions)
    if os.path.exists(model_path):
        state_dict = torch.load(model_path, map_location="cpu", weights_only=True)
        agent.load_state_dict(state_dict)
        print(f"Loaded model from {model_path}")
    else:
        print(f"No model found at {model_path}, using random initialization")
    agent.eval()
    return agent


def write_worker_state(worker_id, iteration, step, total_steps, action_idx,
                       reward, total_reward, minerals, phase, activations=None):
    """Write live worker state to PVC for the monitoring dashboard."""
    state_dir = os.path.join(DATA_DIR, "monitor", "workers")
    os.makedirs(state_dir, exist_ok=True)
    state_path = os.path.join(state_dir, f"worker_{worker_id}.json")

    action_name = "—"
    if 0 <= action_idx < len(ALL_ACTIONS):
        a = ALL_ACTIONS[action_idx]
        if a["action_type"] == "key":
            action_name = f"key:{a['key']}"
        else:
            action_name = f"click({a['x']},{a['y']})"

    state = {
        "worker_id": worker_id,
        "iteration": iteration,
        "step": step,
        "total_steps": total_steps,
        "action_idx": action_idx,
        "action_name": action_name,
        "reward": float(reward),
        "total_reward": float(total_reward),
        "minerals": minerals,
        "phase": phase,
        "timestamp": time.time(),
    }

    # Save activation stats (not full tensors, just summary for dashboard)
    if activations is not None:
        state["activations"] = {}
        for key in ["conv1", "conv2", "conv3"]:
            tensor = activations[key][0]  # first batch element
            # Save per-filter mean activation as list
            state["activations"][key] = {
                "shape": list(tensor.shape),
                "filter_means": tensor.mean(dim=(1, 2)).tolist(),
                "filter_maxs": tensor.amax(dim=(1, 2)).tolist(),
            }
        state["action_probs"] = activations["action_probs"][0].tolist()
        state["value"] = activations["value"][0].item()

    try:
        import json as _json
        with open(state_path, "w") as f:
            _json.dump(state, f)
    except Exception as e:
        print(f"Warning: could not write worker state: {e}")


def save_observation_snapshot(worker_id, obs):
    """Save latest 84x84 observation as raw bytes for the monitor to display."""
    snap_dir = os.path.join(DATA_DIR, "monitor", "snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    snap_path = os.path.join(snap_dir, f"worker_{worker_id}_obs.npy")
    try:
        np.save(snap_path, obs)
    except Exception:
        pass


def save_activation_maps(worker_id, activations):
    """Save conv activation maps as .npy for the monitor to render."""
    act_dir = os.path.join(DATA_DIR, "monitor", "activations")
    os.makedirs(act_dir, exist_ok=True)
    for key in ["conv1", "conv2", "conv3"]:
        path = os.path.join(act_dir, f"worker_{worker_id}_{key}.npy")
        try:
            np.save(path, activations[key][0].numpy())  # (C, H, W)
        except Exception:
            pass


def collect_rollout(env, agent, num_steps):
    """Collect a rollout of transitions."""
    obs_buf = np.zeros((num_steps, 84, 84, 3), dtype=np.uint8)
    actions_buf = np.zeros(num_steps, dtype=np.int64)
    rewards_buf = np.zeros(num_steps, dtype=np.float32)
    dones_buf = np.zeros(num_steps, dtype=np.float32)
    log_probs_buf = np.zeros(num_steps, dtype=np.float32)
    values_buf = np.zeros(num_steps, dtype=np.float32)

    obs, _ = env.reset()
    total_reward = 0.0

    for t in range(num_steps):
        obs_tensor = torch.from_numpy(obs).unsqueeze(0)

        with torch.no_grad():
            action, log_prob, _, value = agent.get_action_and_value(obs_tensor)

        action_int = action.item()
        log_prob_val = log_prob.item()
        value_val = value.item()

        obs_buf[t] = obs
        actions_buf[t] = action_int
        log_probs_buf[t] = log_prob_val
        values_buf[t] = value_val

        # Write live state every 4 steps (reduce I/O)
        if t % 4 == 0:
            with torch.no_grad():
                activations = agent.get_activations(obs_tensor)
            minerals = None
            if hasattr(env, '_last_minerals'):
                minerals = env._last_minerals
            elif hasattr(env, 'env') and hasattr(env.env, '_last_minerals'):
                minerals = getattr(env, '_last_minerals', None)
            write_worker_state(
                WORKER_ID, ITERATION, t, t, action_int,
                rewards_buf[t - 1] if t > 0 else 0.0,
                total_reward, minerals, "collect",
                activations=activations,
            )
            save_observation_snapshot(WORKER_ID, obs)
            save_activation_maps(WORKER_ID, activations)

        obs, reward, terminated, truncated, info = env.step(action_int)

        rewards_buf[t] = reward
        dones_buf[t] = float(terminated or truncated)
        total_reward += reward

        if terminated or truncated:
            obs, _ = env.reset()

    # Compute next value for GAE
    with torch.no_grad():
        next_value = agent.get_value(
            torch.from_numpy(obs).unsqueeze(0)
        ).item()

    # Compute advantages and returns
    advantages, returns = compute_gae(
        rewards_buf, values_buf, dones_buf, next_value,
        gamma=GAMMA, gae_lambda=GAE_LAMBDA,
    )

    # Write final state
    write_worker_state(
        WORKER_ID, ITERATION, num_steps, num_steps, -1,
        0.0, total_reward, None, "saving",
    )

    print(f"Rollout complete: {num_steps} steps, total_reward={total_reward:.4f}")

    return {
        "obs": obs_buf,
        "actions": actions_buf,
        "rewards": rewards_buf,
        "dones": dones_buf,
        "log_probs": log_probs_buf,
        "values": values_buf,
        "advantages": advantages,
        "returns": returns,
    }


def save_rollout(rollout, worker_id, iteration):
    """Save rollout data to PVC as compressed .npz."""
    rollout_dir = os.path.join(DATA_DIR, "rollouts", f"iter_{iteration}")
    os.makedirs(rollout_dir, exist_ok=True)

    npz_path = os.path.join(rollout_dir, f"worker_{worker_id}.npz")
    np.savez_compressed(npz_path, **rollout)
    print(f"Saved rollout to {npz_path}")

    # Write .done marker
    done_path = os.path.join(rollout_dir, f"worker_{worker_id}.done")
    with open(done_path, "w") as f:
        f.write(f"steps={ROLLOUT_STEPS}\n")
    print(f"Wrote done marker: {done_path}")


def main():
    print(f"=== Rollout Worker {WORKER_ID}, Iteration {ITERATION} ===")
    print(f"OpenEnv URL: {OPENENV_URL}")
    print(f"Rollout steps: {ROLLOUT_STEPS}")

    # Wait for OpenEnv sidecar
    if not wait_for_openenv(OPENENV_URL):
        sys.exit(1)

    # Navigate menus
    navigate_starcraft_menus(OPENENV_URL)

    # Create environment
    env = OpenEnvGym(url=OPENENV_URL)
    env = MemoryRewardWrapper(env)

    # Load model
    agent = load_model(ITERATION, NUM_ACTIONS)

    # Collect rollout
    rollout = collect_rollout(env, agent, ROLLOUT_STEPS)

    # Save results
    save_rollout(rollout, WORKER_ID, ITERATION)

    print(f"Worker {WORKER_ID} finished successfully!")


if __name__ == "__main__":
    main()
