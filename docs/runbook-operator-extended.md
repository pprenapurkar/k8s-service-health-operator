# Runbook: Extended Service Health Operator (Part II)

> Ordered by **blast radius**, not frequency: the scariest, least-familiar
> action (force-delete) comes first so an on-call engineer finds it fastest.

## The operator force-deleted a pod (`operator_force_deletes_total > 0`)
1. This should be RARE. Confirm it was justified:
   `kubectl get events --field-selector reason=ForceDelete`
2. Verify the node really was gone at the time:
   `kubectl get node <node>`   # expect NotFound or long-NotReady
3. If the node was actually healthy, DISABLE force-delete immediately:
   ```
   kubectl patch sg <guard> --type=merge \
     -p '{"spec":{"forceDeleteStuckPods":false}}'
   ```
   then investigate why `node_is_gone()` returned true.

## OOM restarts are firing repeatedly (`operator_oom_restarts_total` climbing)
1. The workload is leaking or under-provisioned on memory.
2. Check the escalation: `status.lastOOMAction == "escalate"` means the
   operator gave up and is asking for a human.
3. Fix: raise the memory limit, or adopt VPA to recommend one.
   The operator is surfacing a Design fix it deliberately won't make.

## Advisory findings are growing (`operator_advisory_findings > 0`)
1. List them: `kubectl get sg <guard> -o jsonpath='{.status.advisory}'`
2. These are PREVENTABLE issues (missing limits/probes, :latest, 1 replica).
3. Fix in the manifest + enforce via Kyverno/Gatekeeper so they can't recur.
   Do NOT ask the operator to auto-fix them (by design it won't).

## Dead-pod GC deleted something I wanted to inspect
1. GC only removes terminal pods older than `deadPodTTLMinutes` (default 60).
2. To keep terminal pods longer, raise the TTL on the ServiceGuard.

## Emergency: stop ALL remediation but keep observing
- Switch the guard to advise mode (no mutating actions, still reports):
  `kubectl patch sg <guard> --type=merge -p '{"spec":{"mode":"advise"}}'`
- Or fully stop the operator: scale its Deployment to zero (Part I runbook).
