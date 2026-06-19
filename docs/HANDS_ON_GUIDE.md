# Hands-On Guide — Navigating the Cluster (for newcomers)

This is a guided tour of the running system. Every command below was run on
**this** cluster; the output shown is the **actual** output you'll see (give or
take live numbers and pod-name suffixes). For each command you get: **what it
does**, the **output**, and **what the output means**.

> **Mental model.** Your laptop talks to the cluster with one tool: `kubectl`.
> The cluster (a `kind` cluster running inside Docker) stores **objects** —
> pods, deployments, services, and your custom `ServiceGuard`. Objects live in
> **namespaces** (think folders). Yours are in two namespaces:
> - `default` — the demo app (`demo-app`) and the `ServiceGuard` policy
> - `monitoring` — the operator (`service-health-operator`) and Prometheus
>
> Command shape is always: `kubectl <verb> <type> [name] [-n <namespace>]`.
> Flags you'll use constantly: `-n <ns>` (one namespace), `-A` (all namespaces),
> `-o wide` (more columns), `-o yaml` (full object), `-w` (live watch).

---

## 0. Is everything set up?

The cluster is already created and the operator is already running, so you can
go straight to exploring. If you ever need to (re)build from scratch:

```bash
cd service-health-operator       # the project folder you cloned
make setup     # create cluster + install Prometheus + apply CRD/RBAC/app/guard
make deploy    # build the operator image, load it into kind, run it in-cluster
```

---

## 1. Connecting — which cluster am I talking to?

### `kubectl config current-context`
**Does:** prints the cluster `kubectl` is currently pointed at.
```
kind-operator-lab
```
**Means:** you're talking to the local kind cluster named `operator-lab`. If this
said something else (e.g. a cloud cluster), your other commands would run there.
The `kind-` prefix is just how kind names its context.

### `kubectl config get-contexts`
**Does:** lists every cluster you *could* talk to; `*` marks the active one.
```
CURRENT   NAME                CLUSTER             AUTHINFO            NAMESPACE
*         kind-operator-lab   kind-operator-lab   kind-operator-lab
```
**Means:** you have one context and it's selected. Switch with
`kubectl config use-context <name>` if you had more.

### `kubectl cluster-info`
**Does:** confirms the cluster's control plane is reachable.
```
Kubernetes control plane is running at https://127.0.0.1:49358
CoreDNS is running at https://127.0.0.1:49358/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy
```
**Means:** the cluster's "brain" (API server) is up at that local port, and DNS
is running. If this errors, the cluster/Docker isn't running.

### `kubectl get nodes -o wide`
**Does:** lists the machines that run your workloads. kind uses one container as
one node.
```
NAME                         STATUS   ROLES           AGE   VERSION   INTERNAL-IP   ...   CONTAINER-RUNTIME
operator-lab-control-plane   Ready    control-plane   62m   v1.36.1   172.19.0.2    ...   containerd://2.3.1
```
**Means:** one node, `Ready` (healthy), running Kubernetes v1.36.1. `Ready` is
the key word — if a node were `NotReady`, pods couldn't be scheduled there.

### `kubectl get namespaces`
**Does:** lists the "folders".
```
NAME                 STATUS   AGE
default              Active   62m
kube-node-lease      Active   62m
kube-public          Active   62m
kube-system          Active   62m
local-path-storage   Active   62m
monitoring           Active   61m
```
**Means:** `default` and `monitoring` are yours. `kube-system`, `kube-node-lease`,
`kube-public`, `local-path-storage` are Kubernetes' own internals — you can
ignore them.

---

## 2. Seeing what's running

### `kubectl get pods -n default`
**Does:** lists pods (running containers) in the `default` namespace — your app.
```
NAME                        READY   STATUS    RESTARTS   AGE
demo-app-7c54fb746d-4r64k   1/1     Running   0          41m
demo-app-7c54fb746d-7zk7l   1/1     Running   0          41m
```
**Means:** two `demo-app` pods, each `1/1` (1 of 1 containers ready), `Running`,
with `0` restarts. The long suffix (`7c54fb746d-4r64k`) is auto-generated:
`<deployment>-<replicaset-hash>-<pod-id>`. Two pods because your `ServiceGuard`
floor is `minReplicas: 2`.

### `kubectl get pods -n monitoring`
**Does:** lists the operator and Prometheus pods.
```
NAME                                             READY   STATUS    RESTARTS   AGE
prometheus-kube-state-metrics-75866fb88d-zsjhk   1/1     Running   0          62m
prometheus-prometheus-node-exporter-btjxp        1/1     Running   0          62m
prometheus-server-8cdc5469d-6pbk2                2/2     Running   0          62m
service-health-operator-974b6f86d-wzcrf          1/1     Running   0          59m
```
**Means:** four pods that make the system work:
- `service-health-operator-…` — **your operator** (the brain doing the healing)
- `prometheus-server` — stores metrics (`2/2` = it has 2 containers, both ready)
- `prometheus-kube-state-metrics` — turns Kubernetes object state into metrics
- `prometheus-…-node-exporter` — node-level metrics
All `Running` = the platform is healthy.

> **Tip:** `kubectl get pods -A` shows pods in *every* namespace at once.

### `kubectl get deployments -A`
**Does:** lists Deployments everywhere. A **Deployment** is a controller that
says "keep N identical pods running"; it's the thing you scale, not individual
pods.
```
NAMESPACE            NAME                            READY   UP-TO-DATE   AVAILABLE   AGE
default              demo-app                        2/2     2            2           62m
kube-system          coredns                         2/2     2            2           63m
local-path-storage   local-path-provisioner          1/1     1            1           63m
monitoring           prometheus-kube-state-metrics   1/1     1            1           62m
monitoring           prometheus-server               1/1     1            1           62m
monitoring           service-health-operator         1/1     1            1           59m
```
**Means (column by column):**
- `READY 2/2` — 2 of 2 desired pods are ready (`demo-app`). This is the number
  your operator changes when it scales.
- `UP-TO-DATE` — pods running the latest spec.
- `AVAILABLE` — pods actually serving.
When your operator scales `demo-app` to 6, `demo-app`'s row reads `6/6`.

### `kubectl get all -n monitoring`
**Does:** a convenience view of the common object types in one namespace at once.
```
NAME                                                 READY   STATUS    ...
pod/prometheus-server-8cdc5469d-6pbk2                2/2     Running   ...
pod/service-health-operator-974b6f86d-wzcrf          1/1     Running   ...

NAME                                  TYPE        CLUSTER-IP      PORT(S)    AGE
service/prometheus-server             ClusterIP   10.96.28.161    80/TCP     62m
...

NAME                                                 DESIRED   CURRENT   READY  ...
daemonset.apps/prometheus-prometheus-node-exporter   1         1         1      ...

NAME                                            READY   UP-TO-DATE   AVAILABLE
deployment.apps/service-health-operator         1/1     1            1
...

NAME                                            DESIRED   CURRENT   READY
replicaset.apps/service-health-operator-974b6f86d   1     1         1
```
**Means:** you can see the **layers** that make a Deployment work:
`Deployment → ReplicaSet → Pod`. A **Service** (e.g. `prometheus-server`) is a
stable internal address/load-balancer in front of pods — `ClusterIP` means it's
reachable only inside the cluster, on port 80. (`DaemonSet` = "one pod per node",
used by node-exporter.)

### `kubectl get rs -n default`  (replicasets)
**Does:** lists ReplicaSets — the layer between a Deployment and its Pods. Each
time a Deployment's pod template changes (a new image/command), it makes a new
ReplicaSet.
```
NAME                  DESIRED   CURRENT   READY   AGE
demo-app-58c7d8db68   0         0         0       4h25m
demo-app-7c54fb746d   2         2         2       4h21m
demo-app-867d957594   0         0         0       4h29m
...
```
**Means:** only `demo-app-7c54fb746d` is active (`2` desired/current/ready). The
others are old revisions left at `0` (history, so you can `kubectl rollout undo`).
Every time the demos changed demo-app (crash-loop, OOM), a new ReplicaSet was
born — that's why there are several.

---

## 3. Your custom resource — the `ServiceGuard`

This is the object **you** invented via the CRD. It's the policy the operator
reads, and the operator writes its findings back into the same object's `status`.

### `kubectl get sg`
**Does:** lists ServiceGuards. `sg` is the short alias for `serviceguards`. The
extra columns come from the CRD's `additionalPrinterColumns`.
```
NAME             TARGET     MODE   REPLICAS   CPU%   ADVISORIES
guard-demo-app   demo-app   heal   2          0      2
```
**Means:** the guard `guard-demo-app` watches `demo-app`, is in `heal` mode
(allowed to act), the target currently has `2` replicas, CPU is `0%`, and the
operator has `2` open advisories (preventable issues it's surfacing). This one
line is the operator's whole world at a glance.

> If `CPU%` is blank, the operator currently reads `None` (no fresh metric) — see
> Troubleshooting §9. That's the safe "freeze when blind" state, not a crash.

### `kubectl describe sg guard-demo-app`
**Does:** the full human-readable dump of one object — its `Spec` (your policy),
its `Status` (what the operator decided), and an **Events** timeline at the end.
```
Name:         guard-demo-app
Namespace:    default
API Version:  ops.example.com/v1
Kind:         ServiceGuard
Spec:
  Advisory Enabled:                 true
  Cpu High Percent:                 70
  Cpu Low Percent:                  20
  Force Delete Stuck Pods:          false      # the dangerous one, OFF by default
  Force Delete Only If Node Gone:   true
  Max Replicas:                     6
  Min Replicas:                     2
  Mode:                             heal
  Oom Restart Budget:               3
  Target Deployment:                demo-app
  ...
Status:
  Advisory:
    Container:  demo-app
    Fix:        add a livenessProbe
    Issue:      missing-liveness
    Container:  demo-app
    Fix:        add a readinessProbe
    Issue:      missing-readiness
  Advisory Count:    2
  Current Replicas:  2
  Last OOM Action:   escalate
  Last Restart:      [demo-app-5c6d9545b5-7rqfl]
  Last Scale Reason: cpu=0.0
  Mode:              heal
Events:
  Type     Reason    Age   From   Message
  Normal   Scaled    57m   kopf   Scaled demo-app 2 -> 3 (cpu=83.42397211227164).
  Normal   Scaled    57m   kopf   Scaled demo-app 3 -> 4 (cpu=318.0601925185791).
  Normal   Scaled    56m   kopf   Scaled demo-app 4 -> 5 (cpu=400.0657429305962).
  Normal   Scaled    56m   kopf   Scaled demo-app 5 -> 6 (cpu=266.6362735587482).
  ...
```
**Means:** this single screen tells the whole story —
- **Spec** = the rules you set (scale between 2 and 6, act when CPU >70% / <20%,
  OOM budget 3, force-delete OFF).
- **Status** = what the operator has done/seen: currently 2 replicas, last action
  was an OOM `escalate`, and 2 advisories it wants a human to fix.
- **Events** = a timestamped audit trail. Those `Scaled 2 -> 3 … -> 6` lines are
  the operator's autoscaling captured forever. `describe` is your #1 debugging
  tool: it answers "what is this object and what just happened to it?"

### `kubectl get sg guard-demo-app -o jsonpath='{.status}' | python3 -m json.tool`
**Does:** prints just the operator-written `status` as clean JSON.
```json
{
    "advisory": [
        { "container": "demo-app", "fix": "add a livenessProbe",  "issue": "missing-liveness" },
        { "container": "demo-app", "fix": "add a readinessProbe", "issue": "missing-readiness" }
    ],
    "advisoryCount": 2,
    "currentReplicas": 2,
    "lastOOMAction": "escalate",
    "lastRestart": ["demo-app-5c6d9545b5-7rqfl"],
    "lastScaleReason": "cpu=0.0",
    "mode": "heal"
}
```
**Means:** the machine-readable version of the operator's report.
`-o jsonpath='{.status}'` plucks one field out of the object; piping to
`python3 -m json.tool` just pretty-prints it. Use this when you want the data,
not the prose.

### `kubectl get sg guard-demo-app -o yaml`
**Does:** dumps the *entire* object as YAML (spec + status + Kubernetes
bookkeeping). Big, but the source of truth. Good for copy-pasting a spec.

### `kubectl explain serviceguard.spec.mode`
**Does:** shows the schema/docs for a field — straight from your CRD.
```
FIELD: mode <string>
ENUM:
    heal
    advise
```
**Means:** `mode` is a string that may only be `heal` or `advise`. The API server
learned this from your CRD, so `kubectl explain` documents your custom type just
like a built-in one. Try `kubectl explain serviceguard.spec` to see every field.

---

## 4. Logs — what a program printed

### `kubectl logs -n monitoring deploy/service-health-operator`
**Does:** prints the operator's stdout. `deploy/<name>` means "the pod behind this
deployment".
```
[…] [guard-demo-app] demo-app: replicas=2, cpu=0.0, mode=heal
[…] [guard-demo-app] advisory: 2 finding(s) surfaced for demo-app.
[…] Timer 'reconcile' succeeded.
```
**Means:** one reconcile pass every 30s: it observed `demo-app` (2 replicas, CPU
0%), surfaced 2 advisories, and finished. This is the operator "thinking out
loud." Add `-f` to follow live; add `--tail=20` to see only the last 20 lines;
add `--since=5m` for the last 5 minutes.

```bash
kubectl logs -n monitoring deploy/service-health-operator -f          # live
kubectl logs -n monitoring deploy/service-health-operator --tail=20    # last 20
```

---

## 5. Events — the cluster's timeline

### `kubectl get events -n default --sort-by=.lastTimestamp`
**Does:** lists recent events in a namespace, oldest→newest. Events are short
records of "something happened" (pulled an image, scaled, restarted, failed).
```
57m   Normal   Scaled    serviceguard/guard-demo-app   Scaled demo-app 5 -> 6 (cpu=266...).
...
21s   Normal   Logging   serviceguard/guard-demo-app   [guard-demo-app] demo-app: replicas=2, cpu=None, mode=heal
```
**Means:** a live feed of what the cluster and your operator are doing. When
something looks wrong, events are the fastest way to see *what changed and when*.
(The `Scaled`, `CrashLoopRestart`, `OOMRestart`, `ForceDelete` events are ones
your operator emits on purpose.)

---

## 6. Permissions — what the operator is allowed to do

### `kubectl describe clusterrole service-health-operator`
**Does:** shows the operator's permissions (its "RBAC"). Every line is a thing it
may do; anything not listed is forbidden.
```
Resources                             Verbs
---------                             -----
events                                [create patch]
pods                                  [get list watch delete]
serviceguards.ops.example.com         [get list watch patch update]
serviceguards.ops.example.com/status  [get list watch patch update]
deployments.apps                      [get list watch patch]
deployments.apps/scale                [get list watch patch]
nodes                                 [get list]
namespaces                            [list watch]
```
**Means:** least privilege in action. The operator can scale deployments and
delete pods, but on **nodes** it has only `get list` (read-only) — it can *check*
if a node is gone (for the force-delete guardrail) but can never modify or delete
a node. This is exactly what you'd want a powerful automation to be limited to.

---

## 7. Prometheus' web UI (optional, visual)

```bash
kubectl port-forward -n monitoring svc/prometheus-server 9090:80
```
**Does:** opens a tunnel from `localhost:9090` to the in-cluster Prometheus.
Open <http://localhost:9090> and paste a query, e.g.:
```
100 * avg(rate(container_cpu_usage_seconds_total{pod=~"demo-app-.*", container!=""}[2m])
          / on(pod) group_left
          kube_pod_container_resource_requests{resource="cpu", pod=~"demo-app-.*"})
```
**Means:** that's the *exact* query your operator runs to get `demo-app`'s CPU%.
`Ctrl-C` in the terminal closes the tunnel. (`port-forward` is the general way to
reach any in-cluster service from your laptop.)

---

## 8. The demos — what each one does, and how to watch it

These are `make` shortcuts that run the scripts in `scripts/`. Best watched with
**two terminals**, both in the project folder: one *watching*, one *triggering*.

| Command | What it does under the hood | What to watch |
|---|---|---|
| `make test` | Runs 19 unit tests (`pytest`). **No cluster needed.** | `19 passed` |
| `make setup` | Creates cluster, installs Prometheus, applies CRD + RBAC + demo-app + guard. | Things being created |
| `make deploy` | Builds the operator Docker image, loads it into kind, runs it as a Deployment, tails its logs. | Operator starting + reconcile lines |
| `make spike` | Runs a CPU busy-loop **inside** the demo-app pods. Ctrl-C cleans up (rollout restart) so no load is left behind. | Replicas climb **2→6**, then fall **6→2** |
| `make break` | Patches demo-app to crash (`exit 1`) → CrashLoopBackOff. Operator restarts it. Undo: `kubectl rollout undo deployment/demo-app`. | Pods crashing, operator restart event |
| `make oom` | Patches demo-app to exceed its 64Mi memory limit → OOMKilled. Operator rolling-restarts (budget 3) then **escalates**. | OOMKilled pods, escalate + advisory |
| `make clean` | Deletes the whole kind cluster. | Cluster gone |

**Recommended live demo (autoscaling):**
```bash
# Terminal 1 — the monitor (leave running):
kubectl get deploy demo-app -w
#   you'll see READY go 2/2 → 3/3 → 4/4 → 5/5 → 6/6 under load, then back to 2/2

# Terminal 2 — drive load, then stop it:
make spike            # wait ~2 min: Terminal 1 climbs toward 6/6
#   press Ctrl-C here → load stops → Terminal 1 eases back to 2/2
```
While that runs, a third terminal can show the operator's reasoning:
```bash
kubectl get sg -w                                       # CPU% and REPLICAS update live
kubectl logs -n monitoring deploy/service-health-operator -f   # the decisions
```

> Because the cluster is already set up and the operator already running, you can
> **skip `make setup` / `make deploy`** and jump straight to `make spike` /
> `make break` / `make oom`.

---

## 9. Quick cheat-sheet

```bash
# WHERE AM I
kubectl config current-context
kubectl get nodes
kubectl get ns

# WHAT'S RUNNING
kubectl get pods -A                       # everything
kubectl get pods -n default               # the app
kubectl get deploy -A                     # deployments (what you scale)
kubectl get sg                            # your ServiceGuard

# ZOOM IN
kubectl describe sg guard-demo-app        # spec + status + events
kubectl describe pod <name> -n default    # why a pod is unhealthy
kubectl get sg guard-demo-app -o yaml     # full object

# LIVE
kubectl get deploy demo-app -w            # auto-refresh (Ctrl-C to stop)
kubectl logs -n monitoring deploy/service-health-operator -f

# HISTORY / WHY
kubectl get events -n default --sort-by=.lastTimestamp
```

---

## 10. Troubleshooting & FAQ

**`CPU%` is blank / logs say `cpu=None`.**
Not a bug — it's the operator's **"freeze when blind"** safety rule. It means
Prometheus has no fresh CPU samples for `demo-app` right now (common right after
your laptop sleeps, since the kind containers pause and metrics gap). The operator
deliberately takes **no scaling action** when it can't see clearly. It recovers on
its own once ~2 minutes of fresh scrapes accumulate. Verify with the Prometheus
UI query in §7.

**A pod shows `CrashLoopBackOff` or `OOMKilled`.**
That's expected if you just ran `make break` / `make oom`. Restore the app with:
```bash
kubectl rollout undo deployment/demo-app        # after make break
# or re-apply a clean spec:
kubectl apply -f examples/target-deployment.yaml
kubectl patch deployment demo-app --type=json \
  -p '[{"op":"remove","path":"/spec/template/spec/containers/0/command"}]' 2>/dev/null || true
```

**`make spike` left the app scaled at 6.**
Press `Ctrl-C` in the `make spike` terminal (it auto-cleans). If you killed it
abruptly, run `kubectl rollout restart deployment/demo-app` to clear the load;
CPU drops and the operator scales back to 2 within a few minutes.

**Nothing responds / `connection refused`.**
Docker or the kind cluster isn't running. Check `docker ps`, then
`kubectl get nodes`. If the cluster is gone, `make setup` rebuilds it.

**I want a visual dashboard instead of typing.**
Install **k9s** (`brew install k9s`), run `k9s`, and browse pods/logs/namespaces
with arrow keys. Press `:` then type a resource (e.g. `:deploy`), `l` for logs,
`d` to describe, `Esc` to go back.
