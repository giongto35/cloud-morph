#!/usr/bin/env bash
set -euo pipefail

NS="openenv-training"

echo "=== Kueue Workloads ==="
kubectl get workloads -n "$NS" 2>/dev/null || echo "(no workloads or Kueue not installed)"

echo ""
echo "=== Kueue Queues ==="
kubectl get clusterqueues,localqueues -A 2>/dev/null || echo "(Kueue CRDs not found)"

echo ""
echo "=== Jobs ==="
kubectl get jobs -n "$NS" -o wide

echo ""
echo "=== Pods ==="
kubectl get pods -n "$NS" -o wide

echo ""
echo "=== Trainer Logs (last 20 lines) ==="
kubectl logs job/ppo-trainer -n "$NS" --tail=20 2>/dev/null || echo "(trainer not running)"

echo ""
echo "=== Monitor ==="
kubectl get deployment,svc -n "$NS" -l app=ppo-monitor 2>/dev/null || echo "(monitor not deployed)"
echo ""
echo "Dashboard: kubectl -n $NS port-forward svc/ppo-monitor 9000:9000 → http://localhost:9000"

echo ""
echo "=== Recent Worker Pods ==="
for pod in $(kubectl get pods -n "$NS" -l app=rollout-worker --sort-by=.metadata.creationTimestamp -o name 2>/dev/null | tail -3); do
    echo ""
    echo "--- $pod ---"
    echo "Worker container:"
    kubectl logs "$pod" -n "$NS" -c worker --tail=10 2>/dev/null || echo "(not available)"
done
