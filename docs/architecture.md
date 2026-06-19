# Architecture — Service Health Operator

## The control loop

Everything the operator does is one **reconciliation loop** (observe →
compare → act → record), the same observe-compare-act cycle Kubernetes uses
internally, extended with a richer, metric-aware definition of "healthy". A
kopf timer fires the loop every 30 seconds per ServiceGuard.

The loop is **idempotent** (running it twice with the same inputs yields the
same result — it computes the desired replica count and sets it, never blindly
"add one") and **level-triggered** (it reacts to current state every tick, so
even after a crash the next tick re-observes reality and corrects it).

## Reconciliation flow (Part I §3.2)

```
                       every 30s (kopf timer)
                                │
                                ▼
   ┌────────────────────── THE OPERATOR ──────────────────────┐
   │  read ServiceGuard spec ──▶ desired policy                │
   │        ├──◀── observe ──── Kubernetes API ── replicas,    │
   │        │                                     pod status   │
   │        ├──◀── observe ──── Prometheus ────── avg CPU %    │
   │        ▼                                                  │
   │   ┌── DECIDE ──┐                                          │
   │   │ crashloop? │──yes──▶ restart pod(s) ──┐               │
   │   │ cpu high?  │──yes──▶ scale up         ├──▶ patch      │
   │   │ cpu low?   │──yes──▶ scale down       │   Kubernetes  │
   │   └────────────┘  (clamp to min/max) ─────┘               │
   │        ▼                                                  │
   │   write status + emit metric/event ──▶ ServiceGuard.status│
   └──────────────────────────────────────────────────────────┘
                                │
                                ▼
              target Deployment ▶ pods (healed / scaled)
```

## Extended remediation pipeline (Part II §4.1)

The Part II remediations slot into the same loop as additional, independently
toggleable decide/act pairs. Order is deliberate: cheap/safe cleanups first,
metric-driven scaling last, advisory always.

```
   observe: replicas, pods, pod phases, container states, CPU
                                │
                                ▼
   ┌──────────────── REMEDIATION PIPELINE ────────────────┐
   │ 1. garbage-collect dead pods       (Chronic, safe)    │
   │ 2. restart crash-looping pods      (Part I)           │
   │ 3. restart OOMKilled pods (budget) (Chronic)          │
   │ 4. detect stuck-Terminating; guarded force-delete     │
   │ 5. auto-scale on CPU               (Part I)           │
   │ 6. audit & emit advisory findings  (Design issues)    │
   └───────────────────────────────────────────────────────┘
                                │
                                ▼
   record: status (replicas, cpu, actions, advisory[]) + metrics
```

## heal vs advise mode

Each ServiceGuard has a `mode`:

- **heal** — performs the Chronic-bucket remediations (cleanup, restarts,
  scaling) *and* emits advisory findings.
- **advise** — performs **no** mutating actions; it only observes and reports.
  The safe way to introduce the operator to a new/sensitive workload, or to run
  it cluster-wide as a pure auditor first.

## Blast-radius rails

- Touches only the one deployment named in a ServiceGuard.
- Clamps every scaling decision to `[minReplicas, maxReplicas]`.
- Moves at most one replica per tick (no runaway scale-out from a bad reading).
- Freezes (does nothing) when CPU is unknown — never acts blind.
- Force-delete is opt-in, off by default, and only fires when the node is
  confirmed gone.
- Runs under a least-privilege service account (see `rbac/rbac.yaml`).

## CRD field reference (`ServiceGuard.spec`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `targetDeployment` | string | *(required)* | Deployment to guard |
| `minReplicas` / `maxReplicas` | int | 2 / 6 | Scaling bounds (clamp) |
| `cpuHighPercent` / `cpuLowPercent` | int | 80 / 20 | CPU band that triggers up/down |
| `restartOnCrashLoop` | bool | true | Bounce CrashLoopBackOff pods |
| `prometheusUrl` | string | in-cluster svc | Prometheus HTTP API |
| `mode` | enum | heal | `heal` acts; `advise` only reports |
| `gcDeadPods` / `deadPodTTLMinutes` | bool / int | true / 60 | Dead-pod GC |
| `oomRestartEnabled` / `oomRestartBudget` / `oomWindowMinutes` | bool/int/int | true / 3 / 30 | OOM rolling restart w/ budget |
| `stuckTerminatingDetect` / `stuckTerminatingGraceMinutes` | bool / int | true / 15 | Surface stuck-Terminating pods |
| `forceDeleteStuckPods` / `forceDeleteOnlyIfNodeGone` | bool / bool | **false** / true | Guarded force-delete |
| `advisoryEnabled` | bool | true | Audit Design-bucket issues |
| `scheduleScaleDown` / `quietReplicas` | bool / int | false / 1 | Off-hours non-prod scale-down |

## What runs where

| Component | Where | Lifecycle |
|---|---|---|
| The operator | A Deployment (1 pod) in `monitoring` | Long-running; loops forever |
| ServiceGuard objects | Kubernetes API (etcd) | Created by users; watched by operator |
| Prometheus | Deployment in `monitoring` | Long-running; scrapes continuously |
| Target workload (demo-app) | A Deployment | Guarded; scaled/healed by operator |
