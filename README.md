<h1 align="center">Service Health Operator</h1>

<p align="center">
  <em>A custom Kubernetes operator (Python + kopf) that gives a cluster
  metric-aware self-healing it doesn't have out of the box.</em>
</p>

<p align="center">
  <code>Python 3.11</code> · <code>kopf</code> · <code>Kubernetes</code> ·
  <code>Prometheus / PromQL</code> · <code>kind</code> · <code>RBAC</code>
</p>

---

You declare a **`ServiceGuard`** custom resource — which deployment to watch, the
CPU band, the replica bounds — and the operator runs a reconciliation loop every
30 seconds: it queries Prometheus for CPU, checks pod health, and then **scales**,
**restarts**, **cleans up**, and **surfaces problems** within the limits you set.
It is idempotent and level-triggered like Kubernetes' own controllers, it
**freezes when metrics are unavailable** so it never acts blind, and it runs
in-cluster under a **least-privilege** service account.

```yaml
# This 3-line policy is all a user writes:
apiVersion: ops.example.com/v1
kind: ServiceGuard
metadata: { name: guard-demo-app }
spec:
  targetDeployment: demo-app      # everything else has safe defaults
```

```bash
$ kubectl get sg
NAME             TARGET     MODE   REPLICAS   CPU%   ADVISORIES
guard-demo-app   demo-app   heal   2          0      2
```

## What it does

| Capability | Behaviour | Bucket |
|---|---|---|
| **Auto-scaling** | Scale a deployment up/down on CPU — one step per tick, clamped to `[min,max]`, frozen when CPU is unknown | heal |
| **Crash-loop restart** | Bounce `CrashLoopBackOff` pods, with a restart budget that escalates | heal |
| **Dead-pod GC** | Garbage-collect Evicted/Failed/Completed pods older than a TTL | heal |
| **OOMKill restart** | Rolling-restart OOMKilled workloads with a budget, then **escalate** to a human | heal |
| **Stuck-Terminating** | Surface stuck pods; force-delete **only** when the node is provably gone (opt-in, off by default) | heal/surface |
| **Advisory audit** | Detect preventable issues (missing limits/probes, `:latest`, single replica) and **report** them — never silently auto-fix | surface |
| **Scheduled scale-down** | Optional off-hours scale-down for non-prod | heal |

Guiding philosophy (the part that matters most): **heal the irreducible, surface
the preventable, defer to standard tools for the deep and dangerous — and know
what *not* to automate.**

## See it heal itself

```bash
# Terminal 1 — watch the deployment:
kubectl get deploy demo-app -w

# Terminal 2 — spike CPU, then Ctrl-C to stop:
make spike
```
```
# Terminal 1 shows the deployment "breathe" on its own:
demo-app  2/2 → 3/3 → 4/4 → 5/5 → 6/6   (clamped at maxReplicas under load)
demo-app  6/6 → 5/5 → 4/4 → 3/3 → 2/2   (clamped at minReplicas when idle)
```

Every action is also recorded as a Kubernetes Event and a Prometheus metric:
```
Scaled demo-app 2 -> 3 (cpu=83.4%)        operator_scale_events_total{direction="up"} 4
OOMRestart … after repeated OOMKills      operator_oom_restarts_total 3
```

## Architecture

```
                       every 30s (kopf timer), per ServiceGuard
                                       │
                                       ▼
   observe: replicas, pods, pod phases, container states, CPU (Prometheus)
                                       │
                                       ▼
   ┌──────────────── REMEDIATION PIPELINE ────────────────┐
   │ 1. garbage-collect dead pods       (Chronic, safe)    │
   │ 2. restart crash-looping pods                         │
   │ 3. restart OOMKilled pods (budget) (Chronic)          │
   │ 4. detect stuck-Terminating; guarded force-delete     │
   │ 5. auto-scale on CPU                                   │
   │ 6. audit & emit advisory findings  (Design issues)    │
   └───────────────────────────────────────────────────────┘
                                       │
                                       ▼
   record: status (replicas, cpu, actions, advisory[]) + metrics + Events
```

Full diagram, heal/advise modes, blast-radius rails, and the CRD field reference
are in **[`docs/architecture.md`](docs/architecture.md)**.

## Quick start (local, on `kind`)

**Prerequisites:** Docker, [kind](https://kind.sigs.k8s.io/), `kubectl`, Helm,
Python 3.11.

```bash
git clone <your-repo-url> && cd service-health-operator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

make setup     # cluster + Prometheus + CRD + RBAC + demo-app + sample ServiceGuard
make deploy    # build the operator image, load into kind, run it in-cluster
```

Then drive the demos:

```bash
make test      # 19 unit tests (no cluster needed)
make spike     # CPU autoscaling: up→clamp@6, Ctrl-C → down→clamp@2
make break     # crash-loop heal
make oom       # OOMKill → budgeted rolling-restart → escalate
```

New to Kubernetes? **[`docs/HANDS_ON_GUIDE.md`](docs/HANDS_ON_GUIDE.md)** is a
guided tour of every navigation command with real output and what it means.

## Project structure

```
operator_app/        the operator's Python code
  main.py            kopf handlers + reconcile pipeline + self-metrics + Events
  remediate.py       pure decision logic (scale, restart, GC, OOM, audit, schedule)
  metrics.py         Prometheus query helper (returns None when blind)
  k8s.py             thin wrappers over the Kubernetes client
crd/                 the ServiceGuard CustomResourceDefinition
rbac/                ServiceAccount + ClusterRole + binding (least privilege)
deploy/              Deployment that runs the operator in-cluster
examples/            a target workload + a sample ServiceGuard
tests/               pytest unit tests for the decision logic (no cluster)
scripts/             demo helpers (setup, deploy, break, spike, oom)
docs/                architecture, runbooks, hands-on guide, verification report
```

## Testing

```bash
make test        # or: pytest -v
```
```
tests/test_decide.py ......        # CPU scaling brain (incl. freeze-when-blind)
tests/test_force_delete.py ....    # the critical force-delete safety guardrail
tests/test_gc.py ...               # dead-pod garbage collection
tests/test_oom.py ..               # OOM budget → escalate
tests/test_advisory.py ....        # advisory audit + schedule
============================== 19 passed ==============================
```
The decision logic is written as **pure functions** (data in, plan out, no API
calls), so the operator's brain — including the safety behaviours — is fully
tested without a cluster.

## Design highlights

- **Idempotent & level-triggered** — re-observes reality every tick; safe across
  its own restarts.
- **Freeze when blind** — a metric error returns `None`, not `0`, so a monitoring
  outage can never trick it into scaling down during an incident.
- **Blast-radius rails** — one deployment, one step per tick, clamped to your
  `min/max`, least-privilege RBAC (read-only on nodes).
- **Restraint as a feature** — refuses to force-delete a pod whose node is still
  alive; refuses to auto-fix preventable issues, surfacing them instead.

## Docs

- **[Hands-on guide](docs/HANDS_ON_GUIDE.md)** — navigate the cluster, every command explained
- **[Architecture](docs/architecture.md)** — the loop, modes, rails, CRD reference
- **[Runbook (core)](docs/runbook-operator.md)** & **[Runbook (extended)](docs/runbook-operator-extended.md)**

