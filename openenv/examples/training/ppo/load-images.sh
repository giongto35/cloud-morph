#!/usr/bin/env bash
set -euo pipefail

KIND_CLUSTER="${KIND_CLUSTER:-kueue-demo}"
STARCRAFT_DIR="${STARCRAFT_DIR:-$HOME/games/Starcraft}"

echo "=== Loading images into Kind cluster: $KIND_CLUSTER ==="

# Load Docker images into Kind
for img in openenv:latest openenv-trainer:latest openenv-worker:latest openenv-monitor:latest; do
    echo "Loading $img ..."
    kind load docker-image "$img" --name "$KIND_CLUSTER"
done

echo ""
echo "=== Copying StarCraft game files to Kind node ==="

if [ -d "$STARCRAFT_DIR" ]; then
    # Get the Kind node container name
    NODE_CONTAINER="$(docker ps --filter "name=${KIND_CLUSTER}-control-plane" --format '{{.Names}}')"
    if [ -z "$NODE_CONTAINER" ]; then
        echo "ERROR: Could not find Kind node container"
        exit 1
    fi

    # Create directory on node and copy files
    docker exec "$NODE_CONTAINER" mkdir -p /opt/games/Starcraft
    docker cp "$STARCRAFT_DIR/." "$NODE_CONTAINER:/opt/games/Starcraft/"
    echo "Copied StarCraft files to $NODE_CONTAINER:/opt/games/Starcraft/"
else
    echo "WARNING: StarCraft directory not found at $STARCRAFT_DIR"
    echo "Set STARCRAFT_DIR to the path containing StarCraft.exe"
    echo "Workers will fail without game files, but the architecture demo still works."
fi

echo ""
echo "=== Done ==="
