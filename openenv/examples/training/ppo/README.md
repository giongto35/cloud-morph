# OpenEnv PPO Training Example (Minesweeper)

This directory contains a generic PPO training implementation for Minesweeper using OpenEnv and Stable Baselines 3.

## Structure
- `openenv_gym.py`: Generic Gymnasium wrapper for OpenEnv API.
- `minesweeper_env.py`: Specific environment logic for Minesweeper (Action mapping, Memory reading).
- `train.py`: Training script using PPO MultiInputPolicy.
- `requirements.txt`: Python dependencies.

## Prerequisites
1. **OpenEnv Container Running**:
   Ensure your OpenEnv container is running with the API accessible at `http://localhost:8000`.
   ```bash
   docker run ... -p 8000:8000 ... openenv
   ```

2. **Dependencies**:
   Install the required Python packages on your host machine:
   ```bash
   pip install -r requirements.txt
   ```

## How to Run
Run the training script from this directory:

```bash
cd examples/training/ppo
python3 train.py
```

## Memory Integration
The environment attempts to automatically locate the Minesweeper grid in the container's memory using `examples/local_memory_search.py` (which must be present in the container).
If found, the `memory` observation will contain the raw grid bytes. If not found, it defaults to zeros.
