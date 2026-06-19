#!/usr/bin/env bash
# Spike CPU inside the demo-app pods so utilisation climbs past cpuHighPercent
# and the operator scales up (one step per 30s tick, clamped at maxReplicas).
# Press Ctrl-C to stop: this script then does a rollout restart so NO load is
# left behind (a bare `kubectl exec` busy-loop is NOT killed by Ctrl-C because
# exec without a TTY doesn't forward the signal to the in-pod process).
set -euo pipefail

cleanup() {
  echo; echo "==> Stopping load: rollout restart demo-app (clears all in-pod loops)"
  kubectl rollout restart deployment/demo-app >/dev/null
  echo "==> CPU will decay; the operator scales back down to minReplicas."
  exit 0
}
trap cleanup INT TERM

echo "==> Burning a core in every demo-app pod. Watch in another terminal:"
echo "      kubectl get deploy demo-app -w"
echo "      kubectl get sg guard-demo-app"
echo "==> Press Ctrl-C here to stop the load and let it scale back down."
PIDS=()
for p in $(kubectl get pod -l app=demo-app -o jsonpath='{.items[*].metadata.name}'); do
  kubectl exec "$p" -- sh -c "while true; do :; done" &
  PIDS+=($!)
  echo "    load -> $p"
done
wait "${PIDS[@]}"
