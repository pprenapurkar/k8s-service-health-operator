# Runbook: Service Health Operator (Part I)

## The operator is not acting (no scaling/restarts happening)
1. Is it running? `kubectl get pods -n monitoring -l app=service-health-operator`
2. Read its logs: `kubectl logs -n monitoring deploy/service-health-operator`
3. Is CPU `None`? → Prometheus unreachable or no data; check Prometheus.
4. RBAC `forbidden`? → verify ClusterRole/Binding (`rbac/rbac.yaml`).

## The operator is scaling too aggressively / flapping
1. Check `cpuHighPercent` / `cpuLowPercent` on the ServiceGuard; widen the band.
2. Confirm one-step-per-tick logic; consider a longer timer interval.
3. Inspect the 2m rate window if CPU readings look noisy.

## A pod keeps crash-looping despite restarts
1. The operator backs off after the restart budget (by design — 3 / 10 min).
2. `kubectl describe pod` / `logs` to find the real cause (bad image,
   missing config, failing dependency). Fix the root cause.

## Emergency stop
- Pause all action: scale the operator to zero.
  `kubectl scale deploy/service-health-operator -n monitoring --replicas=0`
- The guarded workloads keep running; they simply stop being auto-managed.
