"""kopf handlers + the reconciliation loop.

Run out-of-cluster for development:
    kopf run operator_app/main.py --verbose
Run in-cluster: packaged into an image and launched by deploy/operator.yaml.

The timer drives one observe -> decide -> act -> record pass per ServiceGuard
every 30 seconds. The remediation pipeline order (Part II §4.1) is deliberate:
cheap/safe cleanups first, metric-driven scaling last, advisory always.
"""
import kopf
from prometheus_client import Counter, Gauge, start_http_server

from operator_app import k8s, metrics, remediate

GROUP = "ops.example.com"
VERSION = "v1"
PLURAL = "serviceguards"

DEFAULT_PROM = "http://prometheus-server.monitoring.svc.cluster.local"

# --------------------------------------------------------------------------
# The operator's own metrics (Part I §16.3 + Part II §13.1)
# --------------------------------------------------------------------------
RESTARTS = Counter("operator_pod_restarts_total",
                   "Pods restarted by the operator", ["deployment"])
SCALES = Counter("operator_scale_events_total",
                 "Scaling actions taken", ["deployment", "direction"])
GC_TOTAL = Counter("operator_dead_pods_collected_total",
                   "Dead pods garbage-collected", ["namespace"])
OOM_TOTAL = Counter("operator_oom_restarts_total",
                    "OOM-triggered rolling restarts", ["deployment"])
FORCE_DEL_TOTAL = Counter("operator_force_deletes_total",
                          "Stuck pods force-deleted", ["namespace"])
ADVISORY_GAUGE = Gauge("operator_advisory_findings",
                       "Open advisory findings", ["deployment"])


@kopf.on.startup()
def _serve_metrics(**_):
    # Prometheus scrapes the operator itself at :8000/metrics
    start_http_server(8000)


# --------------------------------------------------------------------------
# Lifecycle handlers
# --------------------------------------------------------------------------
@kopf.on.create(GROUP, VERSION, PLURAL)
def on_create(spec, name, namespace, logger, **_):
    logger.info(f"ServiceGuard '{name}' created, guarding "
                f"'{spec.get('targetDeployment')}' in {namespace}.")


@kopf.on.update(GROUP, VERSION, PLURAL)
def on_update(spec, name, logger, **_):
    logger.info(f"ServiceGuard '{name}' updated.")


@kopf.on.delete(GROUP, VERSION, PLURAL)
def on_delete(name, logger, **_):
    logger.info(f"ServiceGuard '{name}' deleted; no longer guarding.")


# --------------------------------------------------------------------------
# The reconciliation loop
# --------------------------------------------------------------------------
@kopf.timer(GROUP, VERSION, PLURAL, interval=30.0)
def reconcile(spec, status, name, namespace, patch, logger, body, **_):
    target = spec["targetDeployment"]
    prom = spec.get("prometheusUrl", DEFAULT_PROM)
    mode = spec.get("mode", "heal")
    advisory_findings: list[dict] = []

    # ---- OBSERVE -------------------------------------------------------
    current = k8s.get_replicas(target, namespace)
    cpu = metrics.cpu_utilization_percent(prom, target)
    logger.info(f"[{name}] {target}: replicas={current}, cpu={cpu}, mode={mode}")
    patch.status["currentReplicas"] = current
    patch.status["cpuPercent"] = cpu
    patch.status["mode"] = mode

    # =================== REMEDIATION PIPELINE ===========================

    # 1. garbage-collect dead pods (Chronic, safe) -- Part II §6
    if mode == "heal" and spec.get("gcDeadPods", True):
        pods = k8s.pod_summaries(namespace)
        dead = remediate.find_dead_pods(pods, spec.get("deadPodTTLMinutes", 60))
        for pod_name in dead:
            k8s.delete_pod_simple(pod_name, namespace)
        if dead:
            GC_TOTAL.labels(namespace).inc(len(dead))
            logger.info(f"Garbage-collected {len(dead)} dead pods.")
            patch.status["lastGC"] = dead
            kopf.event(body, type="Normal", reason="DeadPodGC",
                       message=f"Garbage-collected {len(dead)} dead pod(s).")

    # 2. restart crash-looping pods (Part I §12)
    if mode == "heal":
        restarted = remediate.remediate_crashloops(
            target, namespace, spec.get("restartOnCrashLoop", True), logger)
        if restarted:
            RESTARTS.labels(target).inc(len(restarted))
            patch.status["lastRestart"] = restarted
            kopf.event(body, type="Normal", reason="CrashLoopRestart",
                       message=f"Restarted {len(restarted)} crash-looping pod(s).")

    # 3. restart OOMKilled pods (budgeted) (Chronic) -- Part II §7
    if mode == "heal" and spec.get("oomRestartEnabled", True):
        csum = k8s.container_summaries(target, namespace)
        ooms = remediate.count_oomkills(csum)
        action = remediate.decide_oom_action(
            target, ooms, spec.get("oomRestartBudget", 3),
            spec.get("oomWindowMinutes", 30))
        if action == "restart":
            k8s.rollout_restart(target, namespace)
            remediate.record_oom_restart(target)
            OOM_TOTAL.labels(target).inc()
            logger.info(f"OOMKilled detected ({ooms}); rolling-restarted {target}.")
            patch.status["lastOOMAction"] = "restart"
            kopf.event(body, type="Warning", reason="OOMRestart",
                       message=f"Rolling-restarted {target} after repeated OOMKills.")
        elif action == "escalate":
            logger.warning(f"{target} OOMKilling past budget; needs right-sizing.")
            patch.status["lastOOMAction"] = "escalate"
            advisory_findings.append(
                {"issue": "persistent-oom", "detail": "raise memory limit / use VPA"})

    # 4. detect stuck-Terminating; guarded force-delete -- Part II §8
    if spec.get("stuckTerminatingDetect", True):
        pods = k8s.pod_summaries(namespace)
        stuck = remediate.find_stuck_terminating(
            pods, spec.get("stuckTerminatingGraceMinutes", 15))
        for p in stuck:
            advisory_findings.append(
                {"issue": "stuck-terminating", "pod": p["name"], "node": p["node"]})
            gone = k8s.node_is_gone(p["node"])
            if (mode == "heal"
                    and remediate.may_force_delete(
                        spec.get("forceDeleteStuckPods", False),
                        spec.get("forceDeleteOnlyIfNodeGone", True), gone)):
                k8s.force_delete_pod(p["name"], namespace)
                FORCE_DEL_TOTAL.labels(namespace).inc()
                logger.warning(f"Force-deleted stuck pod {p['name']} "
                               f"(node {p['node']} confirmed gone).")
                patch.status.setdefault("lastForceDelete", []).append(p["name"])
                kopf.event(body, type="Warning", reason="ForceDelete",
                           message=f"Force-deleted stuck pod {p['name']}.")
            else:
                logger.info(f"Pod {p['name']} stuck terminating; "
                            f"surfaced (no force-delete).")

    # 5a. scheduled scale-down for non-prod (optional) -- Part II §10
    if spec.get("scheduleScaleDown", False) and mode == "heal":
        import datetime as _dt
        quiet = max(spec.get("minReplicas", 1), spec.get("quietReplicas", 1))
        desired = remediate.scheduled_target_replicas(
            _dt.datetime.now(), normal=spec.get("maxReplicas", 3), quiet=quiet)
        # let CPU-based scaling still raise above this if load demands it
        if desired < current:
            k8s.set_replicas(target, namespace, desired)
            logger.info(f"Scheduled scale-down: {target} -> {desired} replicas.")
            patch.status["currentReplicas"] = desired
            current = desired

    # 5b. auto-scale on CPU (Part I §13)
    if mode == "heal":
        desired = remediate.decide_replicas(current, cpu, spec)
        if remediate.apply_scaling(target, namespace, desired, current, logger):
            direction = "up" if desired > current else "down"
            SCALES.labels(target, direction).inc()
            patch.status["currentReplicas"] = desired
            patch.status["lastScaleReason"] = f"cpu={cpu}"
            kopf.event(body, type="Normal", reason="Scaled",
                       message=f"Scaled {target} {current} -> {desired} (cpu={cpu}).")

    # 6. audit & emit advisory findings (Design issues) -- Part II §9 (always)
    if spec.get("advisoryEnabled", True):
        dep = k8s.deployment_summary(target, namespace)
        advisory_findings.extend(remediate.audit_deployment(dep))

    # ---- RECORD --------------------------------------------------------
    patch.status["advisory"] = advisory_findings
    patch.status["advisoryCount"] = len(advisory_findings)
    ADVISORY_GAUGE.labels(target).set(len(advisory_findings))
    if advisory_findings:
        logger.info(f"[{name}] advisory: {len(advisory_findings)} finding(s) "
                    f"surfaced for {target}.")
