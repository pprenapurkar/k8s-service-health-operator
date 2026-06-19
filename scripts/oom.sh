#!/usr/bin/env bash
# Trigger an OOMKill in a demo-app pod (allocate well past its 64Mi limit) so
# the operator's OOM-aware rolling restart engages, and eventually escalates.
set -euo pipefail
POD=$(kubectl get pod -l app=demo-app -o jsonpath='{.items[0].metadata.name}')
echo "==> Allocating ~256Mi in $POD (limit is 64Mi) -> expect OOMKilled / code 137"
# tail holds the whole stream in memory -> exceeds the limit -> kernel OOM kill
kubectl exec "$POD" -- sh -c "head -c 268435456 /dev/zero | tail" || true
echo "==> Inspect:  kubectl get pods -l app=demo-app"
echo "             kubectl get sg guard-demo-app -o jsonpath='{.status.lastOOMAction}'"
