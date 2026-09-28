"""Unit tests for the translation use case's decision module.

The number fact asserted here is taken from the captured S1 baseline
(``testbed/contracts/sip-baseline/S1-basic-call/``), not invented: the inbound
leg carries ``+8613800138000`` (E.164) and the outbound leg carries
``013800138000`` (national) under POC rule R-MOB-CM-40.

The rest covers the decision matrix of docs/acceptance/test-plan.md §5.1 and
the purity properties of AGENT.md §5 / ADR-0002.
"""

from __future__ import annotations

import socket
import time

import pytest

from as_platform.decision.decide import (
    REASON_MATCH_BLOCK,
    REASON_MATCH_TRANSLATE,
    REASON_NO_MATCH,
    Decision,
    DecisionAction,
    DecisionRequest,
)
from as_platform.decision.rules import Action, Rule, RuleSet
from as_translation.decision import (
    TranslationRule,
    decide_call,
    find_translation_rule,
    translate_number,
)

pytestmark = pytest.mark.unit

# R-MOB-CM-40 of the captured baseline: E.164 -> national, strip "+86", add "0".
_MOBILE_RULE = TranslationRule(
    rule_id="R-MOB-CM-40",
    prefix="+86138",
    strip_prefix="+86",
    add_prefix="0",
)


def _translate_rules() -> RuleSet:
    """A kernel rule set whose only translate range covers +86138."""
    return RuleSet(
        rules=(
            Rule(rule_id="rule-mob-cm-40", prefix="+86138", action=Action.TRANSLATE, target="core"),
            Rule(rule_id="rule-168", prefix="+86168", action=Action.BLOCK),
        )
    )


def _request(called_number: str, received_at: float = 1000.0) -> DecisionRequest:
    return DecisionRequest(
        call_id="call-1",
        calling_number="+86216180001",
        called_number=called_number,
        received_at=received_at,
    )


def test_translate_number_rewrites_the_baseline_number() -> None:
    """The S1 baseline fact: +8613800138000 becomes 013800138000."""
    assert translate_number("+8613800138000", _MOBILE_RULE) == "013800138000"


def test_translate_number_leaves_a_non_matching_number_alone() -> None:
    """A number outside the rule's range is not rewritten."""
    assert translate_number("+8675512345678", _MOBILE_RULE) == "+8675512345678"


def test_find_translation_rule_prefers_the_longest_prefix() -> None:
    """Longest-prefix-first, the same winner rule the kernel matching uses."""
    short = TranslationRule(rule_id="short", prefix="+86755", strip_prefix="+86", add_prefix="0")
    long = TranslationRule(rule_id="long", prefix="+8675512", strip_prefix="+86", add_prefix="0")

    found = find_translation_rule("+8675512345678", (short, long))

    assert found is not None
    assert found.rule_id == "long"


def test_find_translation_rule_returns_none_without_a_match() -> None:
    """No prefix matches, so there is nothing to translate with."""
    assert find_translation_rule("+869990000000", (_MOBILE_RULE,)) is None


def test_decide_call_translates_a_translate_hit() -> None:
    """A translate hit is rewritten by the matching translation rule."""
    decision = decide_call(_request("+8613800138000"), _translate_rules(), (_MOBILE_RULE,))

    assert decision.action is DecisionAction.TRANSLATE
    assert decision.target == "013800138000"
    assert decision.reason_code == REASON_MATCH_TRANSLATE
    assert decision.matched_rule_id == "rule-mob-cm-40"


def test_decide_call_does_not_translate_a_block_hit() -> None:
    """A blocked call is declined as the kernel decided; no rewriting happens."""
    decision = decide_call(_request("+861681000000"), _translate_rules(), (_MOBILE_RULE,))

    assert decision.action is DecisionAction.DECLINE
    assert decision.target is None
    assert decision.reason_code == REASON_MATCH_BLOCK


def test_decide_call_does_not_translate_without_a_match() -> None:
    """No kernel rule matched, so the not-found decision passes through."""
    decision = decide_call(_request("+869990000000"), _translate_rules(), (_MOBILE_RULE,))

    assert decision.action is DecisionAction.NOT_FOUND
    assert decision.target is None
    assert decision.reason_code == REASON_NO_MATCH


def test_decide_call_falls_back_to_the_called_number_without_a_translation_rule() -> None:
    """A translate hit with no translation rule keeps the normalized number."""
    rules = RuleSet(
        rules=(Rule(rule_id="rule-13", prefix="+8613", action=Action.TRANSLATE, target="core"),)
    )

    decision = decide_call(_request("+8613099999999"), rules, ())

    assert decision.action is DecisionAction.TRANSLATE
    assert decision.target == "+8613099999999"


def test_decide_call_is_pure() -> None:
    """The same input produces the same decision, twice."""
    request = _request("+8613800138000")
    first: Decision = decide_call(request, _translate_rules(), (_MOBILE_RULE,))
    second: Decision = decide_call(request, _translate_rules(), (_MOBILE_RULE,))

    assert first == second


def test_decide_call_reads_no_clock_and_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """received_at is injected by the caller; the module never reads time or IO."""
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

    decide_call(_request("+8613800138000"), _translate_rules(), (_MOBILE_RULE,))

    assert clock_reads == []
    assert sockets == []
