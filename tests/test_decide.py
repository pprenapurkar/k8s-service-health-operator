# tests/test_decide.py  (Part I §16.1) -- the CPU scaling brain
from operator_app.remediate import decide_replicas

SPEC = {"minReplicas": 2, "maxReplicas": 6,
        "cpuHighPercent": 80, "cpuLowPercent": 20}


def test_scales_up_one_step_when_hot():
    assert decide_replicas(3, cpu=95, spec=SPEC) == 4


def test_scales_down_one_step_when_cold():
    assert decide_replicas(3, cpu=5, spec=SPEC) == 2


def test_holds_in_normal_band():
    assert decide_replicas(3, cpu=50, spec=SPEC) == 3


def test_never_exceeds_max():
    assert decide_replicas(6, cpu=99, spec=SPEC) == 6


def test_never_drops_below_min():
    assert decide_replicas(2, cpu=1, spec=SPEC) == 2


def test_freezes_when_metric_unknown():
    # The safety test that matters most: a monitoring outage must never
    # trick the operator into scaling.
    assert decide_replicas(4, cpu=None, spec=SPEC) == 4
