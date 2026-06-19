# tests/test_gc.py  (Part II §12.1) -- dead-pod garbage collection
from datetime import datetime, timedelta, timezone

from operator_app.remediate import find_dead_pods

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _pod(name, phase, reason=None, age_min=None):
    finished = None if age_min is None else NOW - timedelta(minutes=age_min)
    return {"name": name, "phase": phase, "reason": reason,
            "finished_at": finished}


def test_collects_old_failed_and_succeeded():
    pods = [_pod("a", "Succeeded", age_min=90),
            _pod("b", "Failed", "Evicted", age_min=120)]
    assert set(find_dead_pods(pods, ttl_minutes=60, now=NOW)) == {"a", "b"}


def test_spares_recently_finished():
    pods = [_pod("fresh", "Succeeded", age_min=5)]
    assert find_dead_pods(pods, ttl_minutes=60, now=NOW) == []


def test_ignores_running_and_missing_timestamp():
    pods = [_pod("run", "Running"),
            _pod("notime", "Failed", age_min=None)]   # no finished_at
    assert find_dead_pods(pods, ttl_minutes=60, now=NOW) == []
