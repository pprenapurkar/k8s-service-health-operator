# tests/test_advisory.py  (Part II §12.4) -- advisory audit + schedule
from datetime import datetime

from operator_app.remediate import audit_deployment, scheduled_target_replicas


def test_audit_flags_all_defects():
    dep = {"replicas": 1, "containers": [
        {"name": "c", "image": "app:latest",
         "has_limits": False, "has_requests": False,
         "has_liveness": False, "has_readiness": False}]}
    issues = {f["issue"] for f in audit_deployment(dep)}
    assert {"single-replica", "missing-resources",
            "missing-liveness", "missing-readiness",
            "mutable-image-tag"} <= issues


def test_audit_clean_deployment_has_no_findings():
    dep = {"replicas": 3, "containers": [
        {"name": "c", "image": "app:1.2.3",
         "has_limits": True, "has_requests": True,
         "has_liveness": True, "has_readiness": True}]}
    assert audit_deployment(dep) == []


def test_schedule_quiets_on_weekend():
    sat = datetime(2026, 6, 6, 14, 0)      # a Saturday afternoon
    assert scheduled_target_replicas(sat, normal=4, quiet=1) == 1


def test_schedule_normal_on_weekday_daytime():
    wed = datetime(2026, 6, 3, 10, 0)      # Wed 10am
    assert scheduled_target_replicas(wed, normal=4, quiet=1) == 4
