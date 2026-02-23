#!/usr/bin/env bash
set -euo pipefail

NS="openenv-training"

echo "=== Cleaning up PPO training resources ==="

# Delete monitor
echo "--- Deleting monitor ---"
kubectl delete deployment ppo-monitor -n "$NS" --ignore-not-found=true
kubectl delete service ppo-monitor -n "$NS" --ignore-not-found=true

# Delete all jobs
echo "--- Deleting jobs ---"
kubectl delete jobs --all -n "$NS" --ignore-not-found=true

# Delete other resources
echo "--- Deleting ConfigMap ---"
kubectl delete configmap worker-job-template -n "$NS" --ignore-not-found=true

echo "--- Deleting PVC ---"
kubectl delete pvc training-data -n "$NS" --ignore-not-found=true

echo "--- Deleting RBAC ---"
kubectl delete rolebinding trainer-rolebinding -n "$NS" --ignore-not-found=true
kubectl delete role trainer-role -n "$NS" --ignore-not-found=true
kubectl delete serviceaccount trainer-sa -n "$NS" --ignore-not-found=true

echo "--- Deleting Kueue resources ---"
kubectl delete localqueue training-queue -n "$NS" --ignore-not-found=true
kubectl delete clusterqueue training-cluster-queue --ignore-not-found=true
kubectl delete resourceflavor default-flavor --ignore-not-found=true

echo "--- Deleting namespace ---"
kubectl delete namespace "$NS" --ignore-not-found=true

echo ""
echo "=== Cleanup complete ==="
