#!/usr/bin/env python3
"""Central PPO trainer that orchestrates distributed rollout workers.

Runs as a Kubernetes Job:
1. Initializes or loads model
2. For each iteration:
   a. Saves model.pt to shared PVC
   b. Creates N worker Jobs via kubectl (Kueue queues & admits them)
   c. Polls PVC for .done files from all workers
   d. Aggregates rollout data, runs PPO update
   e. Saves updated model + checkpoint
"""

import glob
import json
import os
import subprocess
import sys
import time

import numpy as np
import torch

from ppo import CNNAgent, ppo_update

# Configuration
NUM_WORKERS = int(os.environ.get("NUM_WORKERS", "2"))
NUM_ITERATIONS = int(os.environ.get("NUM_ITERATIONS", "3"))
ROLLOUT_STEPS = int(os.environ.get("ROLLOUT_STEPS", "128"))
NUM_ACTIONS = int(os.environ.get("NUM_ACTIONS", "35"))
LEARNING_RATE = float(os.environ.get("LEARNING_RATE", "2.5e-4"))
DATA_DIR = os.environ.get("DATA_DIR", "/data")
NAMESPACE = os.environ.get("NAMESPACE", "openenv-training")
WORKER_TEMPLATE_PATH = os.environ.get(
    "WORKER_TEMPLATE_PATH", "/config/worker-job-template.yaml"
)
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "10"))
WORKER_TIMEOUT = int(os.environ.get("WORKER_TIMEOUT", "600"))


def init_model():
    """Initialize or load existing model."""
    agent = CNNAgent(num_actions=NUM_ACTIONS)
    model_path = os.path.join(DATA_DIR, "model.pt")
    if os.path.exists(model_path):
        state_dict = torch.load(model_path, map_location="cpu", weights_only=True)
        agent.load_state_dict(state_dict)
        print(f"Loaded existing model from {model_path}")
    else:
        print("Initialized new model with random weights")
    return agent


def save_model(agent, iteration=None):
    """Save model to PVC."""
    model_path = os.path.join(DATA_DIR, "model.pt")
    torch.save(agent.state_dict(), model_path)
    print(f"Saved model to {model_path}")

    if iteration is not None:
        ckpt_dir = os.path.join(DATA_DIR, "checkpoints")
        os.makedirs(ckpt_dir, exist_ok=True)
        ckpt_path = os.path.join(ckpt_dir, f"model_iter_{iteration}.pt")
        torch.save(agent.state_dict(), ckpt_path)
        print(f"Saved checkpoint to {ckpt_path}")


def create_worker_jobs(iteration):
    """Create N worker Jobs by substituting the YAML template."""
    print(f"Creating {NUM_WORKERS} worker jobs for iteration {iteration}...")

    with open(WORKER_TEMPLATE_PATH) as f:
        template = f.read()

    for worker_id in range(NUM_WORKERS):
        job_yaml = template.replace("{{WORKER_ID}}", str(worker_id))
        job_yaml = job_yaml.replace("{{ITERATION}}", str(iteration))
        job_yaml = job_yaml.replace("{{ROLLOUT_STEPS}}", str(ROLLOUT_STEPS))

        # Apply via kubectl
        result = subprocess.run(
            ["kubectl", "apply", "-f", "-", "-n", NAMESPACE],
            input=job_yaml,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"ERROR creating worker {worker_id}: {result.stderr}")
        else:
            print(f"Created worker job: worker-{iteration}-{worker_id}")


def wait_for_workers(iteration, num_workers, timeout=None):
    """Poll PVC for .done files from all workers."""
    timeout = timeout or WORKER_TIMEOUT
    rollout_dir = os.path.join(DATA_DIR, "rollouts", f"iter_{iteration}")
    expected = {f"worker_{i}.done" for i in range(num_workers)}

    print(f"Waiting for {num_workers} workers (timeout={timeout}s)...")
    start = time.time()

    while time.time() - start < timeout:
        if os.path.isdir(rollout_dir):
            done_files = set(os.listdir(rollout_dir))
            found = expected & done_files
            print(f"  Progress: {len(found)}/{num_workers} workers done")
            if found == expected:
                print("All workers completed!")
                return True
        time.sleep(POLL_INTERVAL)

    print(f"TIMEOUT: Only {len(found) if os.path.isdir(rollout_dir) else 0}/{num_workers} workers finished")
    return False


def load_rollouts(iteration, num_workers):
    """Load and aggregate rollout data from all workers."""
    rollout_dir = os.path.join(DATA_DIR, "rollouts", f"iter_{iteration}")
    all_obs = []
    all_actions = []
    all_log_probs = []
    all_advantages = []
    all_returns = []

    loaded = 0
    for worker_id in range(num_workers):
        npz_path = os.path.join(rollout_dir, f"worker_{worker_id}.npz")
        if not os.path.exists(npz_path):
            print(f"WARNING: Missing rollout from worker {worker_id}")
            continue

        data = np.load(npz_path)
        all_obs.append(data["obs"])
        all_actions.append(data["actions"])
        all_log_probs.append(data["log_probs"])
        all_advantages.append(data["advantages"])
        all_returns.append(data["returns"])
        loaded += 1

    if loaded == 0:
        return None

    print(f"Loaded rollouts from {loaded}/{num_workers} workers")
    return {
        "obs": np.concatenate(all_obs),
        "actions": np.concatenate(all_actions),
        "log_probs": np.concatenate(all_log_probs),
        "advantages": np.concatenate(all_advantages),
        "returns": np.concatenate(all_returns),
    }


def write_training_state(iteration, phase, stats=None, workers_done=0, num_workers=0):
    """Write training state to PVC for the monitoring dashboard."""
    state_dir = os.path.join(DATA_DIR, "monitor")
    os.makedirs(state_dir, exist_ok=True)
    state_path = os.path.join(state_dir, "trainer.json")

    state = {
        "iteration": iteration,
        "max_iterations": NUM_ITERATIONS,
        "phase": phase,
        "workers_done": workers_done,
        "num_workers": num_workers,
        "timestamp": time.time(),
    }
    if stats:
        state["stats"] = stats

    # Append to metrics history
    metrics_path = os.path.join(state_dir, "metrics.json")
    metrics_history = []
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path) as f:
                metrics_history = json.load(f)
        except Exception:
            metrics_history = []

    if stats:
        metrics_history.append({
            "iteration": iteration,
            "timestamp": time.time(),
            **stats,
        })
        with open(metrics_path, "w") as f:
            json.dump(metrics_history, f)

    with open(state_path, "w") as f:
        json.dump(state, f)


def cleanup_worker_jobs(iteration):
    """Delete worker jobs for this iteration."""
    for worker_id in range(NUM_WORKERS):
        job_name = f"rollout-worker-{iteration}-{worker_id}"
        subprocess.run(
            ["kubectl", "delete", "job", job_name, "-n", NAMESPACE,
             "--ignore-not-found=true"],
            capture_output=True,
            text=True,
        )
    print(f"Cleaned up worker jobs for iteration {iteration}")


def main():
    print("=" * 60)
    print("PPO Distributed Trainer")
    print(f"  Workers: {NUM_WORKERS}")
    print(f"  Iterations: {NUM_ITERATIONS}")
    print(f"  Rollout steps per worker: {ROLLOUT_STEPS}")
    print(f"  Learning rate: {LEARNING_RATE}")
    print("=" * 60)

    # Initialize model and optimizer
    agent = init_model()
    optimizer = torch.optim.Adam(agent.parameters(), lr=LEARNING_RATE, eps=1e-5)

    for iteration in range(NUM_ITERATIONS):
        print(f"\n{'='*60}")
        print(f"ITERATION {iteration}/{NUM_ITERATIONS - 1}")
        print(f"{'='*60}")

        # 1. Save current model for workers to load
        save_model(agent)
        write_training_state(iteration, "saving_model")

        # 2. Create worker jobs
        create_worker_jobs(iteration)
        write_training_state(iteration, "rollout", workers_done=0, num_workers=NUM_WORKERS)

        # 3. Wait for all workers to finish
        all_done = wait_for_workers(iteration, NUM_WORKERS)
        if not all_done:
            print("WARNING: Not all workers finished. Proceeding with available data.")

        # 4. Load and aggregate rollouts
        rollout_data = load_rollouts(iteration, NUM_WORKERS)
        if rollout_data is None:
            print("ERROR: No rollout data available. Skipping update.")
            cleanup_worker_jobs(iteration)
            continue

        # 5. Convert to tensors
        obs_tensor = torch.from_numpy(rollout_data["obs"])
        actions_tensor = torch.from_numpy(rollout_data["actions"])
        log_probs_tensor = torch.from_numpy(rollout_data["log_probs"])
        advantages_tensor = torch.from_numpy(rollout_data["advantages"])
        returns_tensor = torch.from_numpy(rollout_data["returns"])

        # 6. Run PPO update
        write_training_state(iteration, "ppo_update")
        agent.train()
        stats = ppo_update(
            agent, optimizer,
            obs_tensor, actions_tensor, log_probs_tensor,
            advantages_tensor, returns_tensor,
        )
        agent.eval()

        print(f"PPO update: {json.dumps(stats, indent=2)}")
        write_training_state(iteration, "checkpoint", stats=stats,
                             workers_done=NUM_WORKERS, num_workers=NUM_WORKERS)

        # 7. Save checkpoint
        save_model(agent, iteration=iteration)

        # 8. Cleanup worker jobs
        cleanup_worker_jobs(iteration)

    # Final save
    save_model(agent, iteration=NUM_ITERATIONS)
    print("\nTraining complete!")


if __name__ == "__main__":
    main()
