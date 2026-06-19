#!/usr/bin/env bash
# One-command bring-up: cluster prerequisites + Prometheus + CRD + RBAC +
# target workload + sample ServiceGuard. Idempotent; safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER="${CLUSTER:-operator-lab}"

echo "==> Ensuring kind cluster '$CLUSTER' exists"
kind get clusters | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER"
kubectl config use-context "kind-$CLUSTER"

echo "==> Registering the ServiceGuard CRD"
kubectl apply -f crd/serviceguard.yaml

echo "==> Creating monitoring namespace + RBAC"
kubectl get ns monitoring >/dev/null 2>&1 || kubectl create namespace monitoring
kubectl apply -f rbac/rbac.yaml

echo "==> Installing Prometheus (helm)"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install prometheus prometheus-community/prometheus \
  --namespace monitoring \
  --set alertmanager.enabled=false \
  --set prometheus-pushgateway.enabled=false \
  --wait --timeout 5m || true

echo "==> Deploying the target workload + sample ServiceGuard"
kubectl apply -f examples/target-deployment.yaml
kubectl rollout status deploy/demo-app --timeout=120s
kubectl apply -f examples/guard-example.yaml

echo "==> Done. Run the operator with:  PYTHONPATH=. kopf run operator_app/main.py --verbose"
echo "    or in-cluster with:           ./scripts/deploy-incluster.sh"
