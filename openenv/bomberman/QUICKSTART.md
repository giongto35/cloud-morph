# Bomberman Quick Start

Get Bomberman running in 3 steps!

## Step 1: Start the Environment

```bash
cd openenv/bomberman
./run_bomberman.sh
```

Wait ~15 seconds for services to start.

## Step 2: View the Game

Open in your browser:
- **http://localhost:8000/viewer**

## Step 3: Play!

### Option A: Use the Random Agent

```bash
python3 random_bomberman_agent.py --steps 50 --delay 0.2
```

### Option B: Send Actions via API

```bash
# Move right
curl -X POST http://localhost:8000/step \
  -H 'Content-Type: application/json' \
  -d '{"action": {"action_type": "key", "key": 39, "key_state": "down"}}'

# Move down
curl -X POST http://localhost:8000/step \
  -H 'Content-Type: application/json' \
  -d '{"action": {"action_type": "key", "key": 40, "key_state": "down"}}'

# Press Enter
curl -X POST http://localhost:8000/step \
  -H 'Content-Type: application/json' \
  -d '{"action": {"action_type": "key", "key": 13, "key_state": "down"}}'
```

## Controls

- **Arrow Keys**: Move (37=Left, 38=Up, 39=Right, 40=Down)
- **Enter (13)**: Start/Select/Action

## Stop

```bash
docker stop openenv-bomberman
docker rm openenv-bomberman
```

## Need Help?

See `README.md` for detailed documentation.



