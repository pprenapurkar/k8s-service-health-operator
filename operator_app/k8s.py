from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.rest import ApiException


def _load():
    try:
        config.load_incluster_config()   # when running as a pod
    except config.ConfigException:
        config.load_kube_config()        # when running on your laptop


_load()
_apps = client.AppsV1Api()
_core = client.CoreV1Api()


# reads + scaling + crash-loop restart
def get_replicas(deployment: str, namespace: str) -> int:
    dep = _apps.read_namespaced_deployment(deployment, namespace)
    return dep.spec.replicas or 0


def set_replicas(deployment: str, namespace: str, replicas: int) -> None:
    _apps.patch_namespaced_deployment_scale(
        deployment, namespace,
        {"spec": {"replicas": replicas}})


def list_pods(deployment: str, namespace: str):
    # pods of a deployment share its 'app' label in our manifests
    return _core.list_namespaced_pod(
        namespace, label_selector=f"app={deployment}").items


def crashlooping_pods(deployment: str, namespace: str) -> list[str]:
    names = []
    for pod in list_pods(deployment, namespace):
        for cs in (pod.status.container_statuses or []):
            waiting = cs.state.waiting
            if waiting and waiting.reason == "CrashLoopBackOff":
                names.append(pod.metadata.name)
    return names


def restart_pod(pod_name: str, namespace: str) -> None:
    # deleting a managed pod makes the Deployment recreate it
    _core.delete_namespaced_pod(pod_name, namespace)


# Dead-pod garbage collection observation + action
# --------------------------------------------------------------------------

def pod_summaries(namespace: str) -> list[dict]:
    """Normalise every pod in a namespace into a small dict the pure
    decision functions can reason about without touching the client."""
    out = []
    for pod in _core.list_namespaced_pod(namespace).items:
        st = pod.status
        finished = None
        # use the latest container finish time if present
        for cs in (st.container_statuses or []):
            term = cs.state.terminated if cs.state else None
            if term and term.finished_at:
                finished = term.finished_at
        out.append({
            "name": pod.metadata.name,
            "phase": st.phase,
            "reason": getattr(st, "reason", None),
            "finished_at": finished,
            "deletion_timestamp": pod.metadata.deletion_timestamp,
            "node": pod.spec.node_name,
        })
    return out


def delete_pod_simple(name: str, namespace: str) -> None:
    _core.delete_namespaced_pod(name, namespace)


# OOMKill detection + rolling restart
# -------------------------------------------------------------------------------------
def container_summaries(deployment: str, namespace: str) -> list[dict]:
    """Per-container OOM flags for a deployment's pods.

    container_summary = {pod, container, oom_current(bool), oom_last(bool)}.
    A container is OOM-flagged if its current *or* last terminated state
    carries reason 'OOMKilled' (exit code 137).
    """
    out = []
    for pod in list_pods(deployment, namespace):
        for cs in (pod.status.container_statuses or []):
            cur = cs.state.terminated if cs.state else None
            last = cs.last_state.terminated if cs.last_state else None
            oom_current = bool(cur and cur.reason == "OOMKilled")
            oom_last = bool(last and last.reason == "OOMKilled")
            out.append({
                "pod": pod.metadata.name,
                "container": cs.name,
                "oom_current": oom_current,
                "oom_last": oom_last,
            })
    return out


def rollout_restart(deployment: str, namespace: str) -> None:
    """Same effect as 'kubectl rollout restart': patch a template
    annotation so Kubernetes rolls all pods gracefully."""
    now = datetime.now(timezone.utc).isoformat()
    body = {"spec": {"template": {"metadata": {"annotations": {
        "ops.example.com/restartedAt": now}}}}}
    _apps.patch_namespaced_deployment(deployment, namespace, body)


# Stuck-Terminating guarded force-delete
# --------------------------------------------------------------------------
def node_is_gone(node_name: str | None) -> bool:
    """True if the node object no longer exists -> kubelet cannot run pods."""
    if not node_name:
        return False
    try:
        _core.read_node(node_name)
        return False  # node still exists; NOT safe to assume gone
    except ApiException as e:
        return e.status == 404  # 404 -> node truly removed


def force_delete_pod(name: str, namespace: str) -> None:
    _core.delete_namespaced_pod(
        name, namespace,
        grace_period_seconds=0,  # immediate
        body=client.V1DeleteOptions(grace_period_seconds=0))


# Advisory audit observation
# --------------------------------------------------------------------------
def deployment_summary(deployment: str, namespace: str) -> dict:
    """Simplified view of a deployment's pod template for the advisory audit.

    dep = {replicas, containers:[{name,image,has_limits,has_requests,
           has_liveness,has_readiness}]}
    """
    dep = _apps.read_namespaced_deployment(deployment, namespace)
    containers = []
    for c in (dep.spec.template.spec.containers or []):
        res = c.resources
        has_limits = bool(res and res.limits)
        has_requests = bool(res and res.requests)
        containers.append({
            "name": c.name,
            "image": c.image or "",
            "has_limits": has_limits,
            "has_requests": has_requests,
            "has_liveness": c.liveness_probe is not None,
            "has_readiness": c.readiness_probe is not None,
        })
    return {"replicas": dep.spec.replicas or 1, "containers": containers}
