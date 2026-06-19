# tests/test_force_delete.py  (Part II §12.3) -- THE critical safety test.
# These encode the force-delete safety contract as executable promises: no
# future refactor can make the operator force-delete a pod whose node is still
# alive, or force-delete when the feature is disabled.
from operator_app.remediate import may_force_delete


def test_refuses_when_feature_disabled():
    assert may_force_delete(force_enabled=False,
                            require_node_gone=True, node_gone=True) is False


def test_refuses_when_node_still_alive():
    # the dangerous case: feature on, but node NOT gone -> must refuse
    assert may_force_delete(force_enabled=True,
                            require_node_gone=True, node_gone=False) is False


def test_allows_only_when_node_confirmed_gone():
    assert may_force_delete(force_enabled=True,
                            require_node_gone=True, node_gone=True) is True


def test_opt_out_guardrail_is_explicit():
    # disabling the guardrail is possible but must be a deliberate choice
    assert may_force_delete(force_enabled=True,
                            require_node_gone=False, node_gone=False) is True
