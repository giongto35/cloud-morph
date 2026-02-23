#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OPENENV_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "=== Building Docker images ==="

# 1. Build OpenEnv base image (x86_64 for Wine compatibility)
echo ""
echo "--- Building openenv:latest (linux/amd64 for Wine) ---"
docker build --platform linux/amd64 -t openenv:latest "$OPENENV_ROOT"

# 2. Build trainer image
echo ""
echo "--- Building openenv-trainer:latest ---"
docker build -t openenv-trainer:latest -f "$SCRIPT_DIR/Dockerfile.trainer" "$SCRIPT_DIR"

# 3. Build worker image
echo ""
echo "--- Building openenv-worker:latest ---"
docker build -t openenv-worker:latest -f "$SCRIPT_DIR/Dockerfile.worker" "$SCRIPT_DIR"

# 4. Build monitor image
echo ""
echo "--- Building openenv-monitor:latest ---"
docker build -t openenv-monitor:latest -f "$SCRIPT_DIR/Dockerfile.monitor" "$SCRIPT_DIR"

echo ""
echo "=== All images built successfully ==="
docker images | grep -E "openenv|REPOSITORY"
