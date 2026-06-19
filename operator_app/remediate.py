"""Remediation logic: pure decision functions + thin action helpers.

Design discipline (Part I §13.2, Part II §4.4): every *decision* is a pure
function -- data in, plan out, no API calls -- so it is trivially unit-testable
without a cluster. The functions that actually touch Kubernetes import the
``k8s`` module lazily, so importing this module for tests never requires a
cluster or a kubeconfig.
"""
import time
from datetime import datetime, timezone

# ==========================================================================
# Part I §12: crash-loop restart with a budget
# ==========================================================================
# remember recent restarts per pod to avoid infinite churn
_restart_log: dict[str, list[float]] = {}
_MAX_RESTARTS = 3
_WINDOW_SEC = 600          # 10 minutes


def _recently_restarted(pod: str) -> int:
    now = time.time()
    history = [t for t in _restart_log.get(pod, []) if now - t < _WINDOW_SEC]
    _restart_log[pod] = history
    return len(history)


def remediate_crashloops(target: str, namespace: str,
                         enabled: bool, logger) -> list[str]:
    if not enabled:
        return []
    from operator_app import k8s          # lazy: keep pure tests cluster-free
    restarted = []
    for pod in k8s.crashlooping_pods(target, namespace):
        if _recently_restarted(pod) >= _MAX_RESTARTS:
            logger.warning(f"Pod {pod} crash-looping past restart budget; "
                           f"backing off for a human to investigate.")
            continue
        k8s.restart_pod(pod, namespace)
        _restart_log.setdefault(pod, []).append(time.time())
        restarted.append(pod)
        logger.info(f"Restarted crash-looping pod {pod}.")
    return restarted


# ==========================================================================
# Part I §13: CPU-based auto-scaling decision (pure) + action
# ==========================================================================
def decide_replicas(current: int, cpu: float | None, spec: dict) -> int:
    """Pure decision: returns the desired replica count.
    Returns 'current' unchanged when CPU is unknown."""
    lo = spec.get("minReplicas", 2)
    hi = spec.get("maxReplicas", 6)
    high = spec.get("cpuHighPercent", 80)
    low = spec.get("cpuLowPercent", 20)

    if cpu is None:                    # blind -> do not act
        return current

    target = current
    if cpu > high and current < hi:
        target = current + 1           # one step up
    elif cpu < low and current > lo:
        target = current - 1           # one step down
    return max(lo, min(hi, target))    # clamp to bounds


def apply_scaling(target: str, namespace: str,
                  desired: int, current: int, logger) -> bool:
    if desired == current:
        return False
    from operator_app import k8s          # lazy import
    k8s.set_replicas(target, namespace, desired)
    logger.info(f"Scaled {target}: {current} -> {desired} replicas.")
    return True


# ==========================================================================
# Part II §6: dead-pod garbage collection (pure)
# ==========================================================================
def find_dead_pods(pod_summaries: list[dict], ttl_minutes: int,
                   now: datetime | None = None) -> list[str]:
    """Return names of terminal pods older than the TTL.
    pod_summary = {name, phase, reason, finished_at(datetime|None)}"""
    now = now or datetime.now(timezone.utc)
    dead = []
    for p in pod_summaries:
        terminal = (p["phase"] in ("Succeeded", "Failed")
                    or p.get("reason") == "Evicted")
        if not terminal:
            continue
        finished = p.get("finished_at")
        if finished is None:
            # no timestamp -> be conservative, skip this pass
            continue
        age_min = (now - finished).total_seconds() / 60.0
        if age_min >= ttl_minutes:
            dead.append(p["name"])
    return dead


# ==========================================================================
# Part II §7: OOMKill-aware controlled restart (pure detection/decision)
# ==========================================================================
_oom_log: dict[str, list[float]] = {}   # deployment -> recent OOM action times


def count_oomkills(container_summaries: list[dict]) -> int:
    """container_summary = {pod, oom_current(bool), oom_last(bool)}.
    Counts containers showing an OOMKilled signal now or in last state."""
    return sum(1 for c in container_summaries
               if c.get("oom_current") or c.get("oom_last"))


def decide_oom_action(deployment: str, oom_count: int,
                      budget: int, window_min: int,
                      now: float | None = None) -> str:
    """Returns 'restart', 'escalate', or 'noop'."""
    if oom_count == 0:
        return "noop"
    now = now or time.time()
    window = window_min * 60
    history = [t for t in _oom_log.get(deployment, []) if now - t < window]
    _oom_log[deployment] = history
    if len(history) >= budget:
        return "escalate"               # persistent -> stop, alert a human
    return "restart"


def record_oom_restart(deployment: str, now: float | None = None) -> None:
    _oom_log.setdefault(deployment, []).append(now or time.time())


# ==========================================================================
# Part II §8: stuck-Terminating detection + force-delete safety gate (pure)
# ==========================================================================
def find_stuck_terminating(pod_summaries: list[dict], grace_minutes: int,
                           now: datetime | None = None) -> list[dict]:
    """Return summaries of pods terminating longer than the grace window."""
    now = now or datetime.now(timezone.utc)
    stuck = []
    for p in pod_summaries:
        ts = p.get("deletion_timestamp")
        if ts is None:
            continue
        age_min = (now - ts).total_seconds() / 60.0
        if age_min >= grace_minutes:
            stuck.append(p)
    return stuck


def may_force_delete(force_enabled: bool, require_node_gone: bool,
                     node_gone: bool) -> bool:
    """The safety gate. Default policy: only when the node is gone."""
    if not force_enabled:
        return False
    if require_node_gone:
        return node_gone               # safe path: container cannot still run
    return True                        # opt-out path: caller accepted the risk


# ==========================================================================
# Part II §9: advisory audit of preventable (Design-bucket) issues (pure)
# ==========================================================================
def audit_deployment(dep: dict) -> list[dict]:
    """Pure audit over a simplified deployment dict. Returns findings.
    dep = {replicas, containers:[{name,image,has_limits,has_requests,
           has_liveness,has_readiness}]}"""
    findings = []
    if dep.get("replicas", 1) < 2:
        findings.append({"issue": "single-replica",
                         "fix": "raise replicas >=2 and add anti-affinity"})
    for c in dep.get("containers", []):
        n = c.get("name")
        if not c.get("has_limits") or not c.get("has_requests"):
            findings.append({"issue": "missing-resources", "container": n,
                             "fix": "set requests+limits; enforce via LimitRange"})
        if not c.get("has_liveness"):
            findings.append({"issue": "missing-liveness", "container": n,
                             "fix": "add a livenessProbe"})
        if not c.get("has_readiness"):
            findings.append({"issue": "missing-readiness", "container": n,
                             "fix": "add a readinessProbe"})
        img = c.get("image", "")
        if img.endswith(":latest") or ":" not in img:
            findings.append({"issue": "mutable-image-tag", "container": n,
                             "fix": "pin an image digest or fixed tag"})
    return findings


# ==========================================================================
# Part II §10: scheduled scale-down for non-prod (pure)
# ==========================================================================
def scheduled_target_replicas(now: datetime, normal: int,
                              quiet: int,
                              quiet_start_hour: int = 20,
                              quiet_end_hour: int = 7) -> int:
    """Return the replica count the schedule implies for 'now'.
    Weekends and weeknight off-hours -> 'quiet'; otherwise 'normal'."""
    is_weekend = now.weekday() >= 5            # Sat=5, Sun=6
    h = now.hour
    off_hours = (h >= quiet_start_hour or h < quiet_end_hour)
    return quiet if (is_weekend or off_hours) else normal
