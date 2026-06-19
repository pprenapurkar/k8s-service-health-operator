#!/usr/bin/env bash
# Build the operator image, load it into kind, and run it in-cluster.
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER="${CLUSTER:-operator-lab}"
IMAGE="service-health-operator:0.1.0"

echo "==> Building $IMAGE"
docker build -t "$IMAGE" .

echo "==> Loading image into kind cluster '$CLUSTER'"
kind load docker-image "$IMAGE" --name "$CLUSTER"

echo "==> Applying the operator Deployment"
kubectl apply -f deploy/operator.yaml
kubectl rollout status -n monitoring deploy/service-health-operator --timeout=120s

echo "==> Operator logs (Ctrl-C to stop):"
kubectl logs -n monitoring deploy/service-health-operator -f
