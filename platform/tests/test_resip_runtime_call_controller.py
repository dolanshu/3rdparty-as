"""Unit tests: ResipRuntimeListener invite path through CallController."""

from __future__ import annotations

import pytest

from as_platform.decision import RuleSet, decide
from as_platform.decision.decide import DecisionRequest
from as_platform.decision.rules import Action, Rule
from as_platform.sip.call_controller import CallController, LegId
from as_platform.sip.resip_runtime import (
    controller_effects_for_inbound_invite,
    status_code_from_controller_effects,
)

pytestmark = pytest.mark.unit


def test_reject_decision_maps_to_sip_status() -> None:
    controller = CallController()
    request = DecisionRequest(
        call_id="cid-reject@127.0.0.1",
        calling_number="+15551230001",
        called_number="+15558675309",
        received_at=1.0,
    )
    decision = decide(request, RuleSet(rules=()))
    effects = controller_effects_for_inbound_invite(controller, "cid-reject@127.0.0.1", decision)
    assert status_code_from_controller_effects(effects) == 404
    assert controller.active_call_count() == 0


def test_forward_decision_registers_controller_state() -> None:
    controller = CallController()
    rules = RuleSet(
        rules=(
            Rule(
                rule_id="fwd",
                prefix="+15558675309",
                action=Action.FORWARD,
                target="sip:downstream@127.0.0.1:5060",
            ),
        )
    )
    request = DecisionRequest(
        call_id="cid-fwd@127.0.0.1",
        calling_number="+15551230001",
        called_number="+15558675309",
        received_at=1.0,
    )
    decision = decide(request, rules)
    effects = controller_effects_for_inbound_invite(controller, "cid-fwd@127.0.0.1", decision)
    assert status_code_from_controller_effects(effects) == 0
    assert controller.active_call_count() == 1
    correlation = controller.correlation_for_inbound(LegId(call_id="cid-fwd@127.0.0.1"))
    assert correlation is not None
    assert correlation.outbound is None
