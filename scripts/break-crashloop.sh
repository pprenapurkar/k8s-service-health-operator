#!/usr/bin/env bash
# Force demo-app into CrashLoopBackOff so the operator's restart path engages.
# Revert with:  kubectl rollout undo deployment/demo-app
set -euo pipefail
echo "==> Patching demo-app with a command that exits immediately"
kubectl patch deployment demo-app --type=json -p \
  '[{"op":"add","path":"/spec/template/spec/containers/0/command",
     "value":["sh","-c","exit 1"]}]'
echo "==> Watch it crash-loop, then the operator restart (up to the budget):"
echo "    kubectl get pods -l app=demo-app -w"
echo "==> Revert with:  kubectl rollout undo deployment/demo-app"
