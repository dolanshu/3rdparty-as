"""Unit tests for the decide() pure function.

Acceptance: docs/acceptance/test-plan.md §5.1 (the seven-case decision matrix)
plus the purity properties of AGENT.md §5 and ADR-0002.
"""

from __future__ import annotations

import socket
import time

import pytest

from as_platform.decision.decide import (
    REASON_MATCH_BLOCK,
    REASON_MATCH_FORWARD,
    REASON_MATCH_TRANSLATE,
    REASON_NO_MATCH,
    Decision,
    DecisionAction,
    DecisionRequest,
    decide,
)
from as_platform.decision.rules import Action, Rule, RuleSet

pytestmark = pytest.mark.unit


def _rules() -> RuleSet:
    """The four-rule fixture of test-plan §5.1."""
    return RuleSet(
        rules=(
            Rule(rule_id="rule-755", prefix="+86755", action=Action.TRANSLATE, target="return-uas"),
            Rule(
                rule_id="rule-75512",
                prefix="+8675512",
                action=Action.TRANSLATE,
                target="return-uas",
            ),
            Rule(rule_id="rule-138", prefix="+86138", action=Action.FORWARD),
            Rule(rule_id="rule-168", prefix="+86168", action=Action.BLOCK),
        )
    )


def _conflict_rules() -> RuleSet:
    """A number range covered by both a translate and a block rule. REQ-F-7."""
    return RuleSet(
        rules=(
            Rule(rule_id="rule-16", prefix="+8616", action=Action.TRANSLATE, target="return-uas"),
            Rule(rule_id="rule-168", prefix="+86168", action=Action.BLOCK),
        )
    )


def _request(called_number: str, received_at: float = 1000.0) -> DecisionRequest:
    return DecisionRequest(
        call_id="call-1",
        calling_number="+867550000000",
        called_number=called_number,
        received_at=received_at,
    )


@pytest.mark.parametrize(
    ("called_number", "rules", "action", "reason_code", "target", "matched_rule_id"),
    [
        # 1: translate hit on +86755.
        (
            "+867550123456",
            "base",
            DecisionAction.TRANSLATE,
            REASON_MATCH_TRANSLATE,
            "return-uas",
            None,
        ),
        # 2: both +86755 and +8675512 match; the longer prefix wins.
        (
            "+8675512345678",
            "base",
            DecisionAction.TRANSLATE,
            REASON_MATCH_TRANSLATE,
            "return-uas",
            "rule-75512",
        ),
        # 3: block hit -> 603 Decline, no outbound leg. REQ-F-7.
        ("+861681000000", "base", DecisionAction.DECLINE, REASON_MATCH_BLOCK, None, "rule-168"),
        # 4: forward hit.
        (
            "+8613800000000",
            "base",
            DecisionAction.FORWARD,
            REASON_MATCH_FORWARD,
            "+8613800000000",
            "rule-138",
        ),
        # 5: no rule matched -> 404 Not Found. REQ-F-6.
        ("+869990000000", "base", DecisionAction.NOT_FOUND, REASON_NO_MATCH, None, None),
        # 6: a number without '+' is equivalent to case 1 after normalization.
        (
            "867551234567",
            "base",
            DecisionAction.TRANSLATE,
            REASON_MATCH_TRANSLATE,
            "return-uas",
            None,
        ),
        # 7: block outranks translate. REQ-F-7.
        ("+861681000000", "conflict", DecisionAction.DECLINE, REASON_MATCH_BLOCK, None, "rule-168"),
    ],
)
def test_decision_matrix(
    called_number: str,
    rules: str,
    action: DecisionAction,
    reason_code: str,
    target: str | None,
    matched_rule_id: str | None,
) -> None:
    """The seven cases of the test-plan §5.1 decision matrix."""
    rule_set = _conflict_rules() if rules == "conflict" else _rules()
    decision = decide(_request(called_number), rule_set)

    assert decision.action is action
    assert decision.reason_code == reason_code
    assert decision.target == target
    if matched_rule_id is not None:
        assert decision.matched_rule_id == matched_rule_id


def test_decide_is_pure() -> None:
    """The same input produces the same decision, twice."""
    request = _request("+867551234567")
    first: Decision = decide(request, _rules())
    second: Decision = decide(request, _rules())

    assert first == second


def test_received_at_does_not_change_the_decision() -> None:
    """received_at is carried by the caller; it never influences the outcome."""
    early = decide(_request("+867551234567", received_at=0.0), _rules())
    late = decide(_request("+867551234567", received_at=9_999_999.0), _rules())

    assert early == late


def test_decide_reads_no_clock_and_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """A decision module that touched time or the network would fail here."""
    clock_reads: list[str] = []
    sockets: list[str] = []

    def fake_time() -> float:
        clock_reads.append("time")
        return 0.0

    def fake_monotonic() -> float:
        clock_reads.append("monotonic")
        return 0.0

    def fake_socket(*args: object, **kwargs: object) -> None:
        sockets.append("socket")

    monkeypatch.setattr(time, "time", fake_time)
    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    monkeypatch.setattr(socket, "socket", fake_socket)

    decide(_request("+867551234567"), _rules())

    assert clock_reads == []
    assert sockets == []


def test_calling_number_is_not_the_match_target() -> None:
    """Matching runs on the called number, not on the calling number."""
    request = DecisionRequest(
        call_id="call-1",
        calling_number="+861681000000",
        called_number="+8613800000000",
        received_at=1000.0,
    )

    decision = decide(request, _rules())

    assert decision.action is DecisionAction.FORWARD
