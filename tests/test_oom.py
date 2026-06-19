# tests/test_oom.py  (Part II §12.2) -- OOM budget + escalation
from operator_app import remediate


def test_restarts_then_escalates():
    remediate._oom_log.clear()
    # within budget=2 -> restart twice, then escalate
    assert remediate.decide_oom_action("svc", 1, budget=2, window_min=30,
                                        now=1000) == "restart"
    remediate.record_oom_restart("svc", now=1000)
    assert remediate.decide_oom_action("svc", 1, budget=2, window_min=30,
                                        now=1001) == "restart"
    remediate.record_oom_restart("svc", now=1001)
    assert remediate.decide_oom_action("svc", 1, budget=2, window_min=30,
                                        now=1002) == "escalate"


def test_noop_when_no_oom():
    assert remediate.decide_oom_action("svc2", 0, 3, 30) == "noop"
