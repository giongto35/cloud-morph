#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
K8S_DIR="$SCRIPT_DIR/k8s"

echo "=== Deploying PPO training to Kubernetes ==="

# 1. Create namespace
echo "--- Creating namespace ---"
kubectl apply -f "$K8S_DIR/namespace.yaml"

# 2. Create PVC
echo "--- Creating PVC ---"
kubectl apply -f "$K8S_DIR/pvc.yaml"

# 3. Create RBAC
echo "--- Creating RBAC ---"
kubectl apply -f "$K8S_DIR/rbac.yaml"

# 4. Create Kueue resources
echo "--- Creating Kueue resources ---"
kubectl apply -f "$K8S_DIR/kueue-resources.yaml"

# 5. Create worker job template ConfigMap
echo "--- Creating worker job template ConfigMap ---"
kubectl -n openenv-training create configmap worker-job-template \
    --from-file=worker-job-template.yaml="$K8S_DIR/worker-job-template.yaml" \
    --dry-run=client -o yaml | kubectl apply -f -

# 6. Create trainer job
echo "--- Creating trainer job ---"
kubectl apply -f "$K8S_DIR/trainer-job.yaml"

# 7. Deploy monitoring dashboard
echo "--- Deploying monitor dashboard ---"
kubectl apply -f "$K8S_DIR/monitor.yaml"

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Dashboard (port-forward):"
echo "  kubectl -n openenv-training port-forward svc/ppo-monitor 9000:9000"
echo "  open http://localhost:9000"
echo ""
echo "Or run monitor locally:"
echo "  DATA_DIR=./data python monitor.py"
echo ""
echo "Monitor with:"
echo "  $SCRIPT_DIR/status.sh"
echo "  kubectl -n openenv-training logs job/ppo-trainer -f"
