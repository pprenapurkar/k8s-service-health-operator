"""Prometheus query helpers.

The operator's metric sense: it asks Prometheus the CPU-utilisation question
over HTTP and parses the answer into a single number it can reason about.
Crucially it returns ``None`` (not 0) when Prometheus has no data or is
unreachable, so the decision logic can choose to *freeze* when blind.
"""
import requests


def cpu_utilization_percent(prometheus_url: str,
                            deployment: str,
                            window: str = "2m") -> float | None:
    """Return avg CPU utilisation (%) across a deployment's pods,
    or None if Prometheus has no data yet / is unreachable."""
    query = (
        f'100 * avg('
        f'  rate(container_cpu_usage_seconds_total'
        f'    {{pod=~"{deployment}-.*", container!=""}}[{window}])'
        f'  / on(pod) group_left '
        f'  kube_pod_container_resource_requests'
        f'    {{resource="cpu", pod=~"{deployment}-.*"}}'
        f')'
    )
    try:
        resp = requests.get(f"{prometheus_url}/api/v1/query",
                            params={"query": query}, timeout=5)
        resp.raise_for_status()
        result = resp.json()["data"]["result"]
        if not result:
            return None                      # no samples yet
        return float(result[0]["value"][1])
    except (requests.RequestException, KeyError, ValueError):
        return None                          # treat errors as 'unknown'
