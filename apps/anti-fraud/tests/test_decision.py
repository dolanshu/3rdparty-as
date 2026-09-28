"""Unit tests for the anti-fraud use case's decision module.

The kernel answers first and this module only screens what the kernel would let
through: a call the kernel declines stays declined (REQ-F-7), and a number
outside every configured range stays NOT_FOUND because it is not this use case's
business at all (REQ-F-6). Only FORWARD and TRANSLATE are re-examined, against a
rate window whose counter is **injected** by the caller — the window itself
lives in the state store, never in this process (ADR-0002).

The number ranges are taken from the acceptance matrix
(``docs/acceptance/test-plan.md`` §5.1): ``+86168`` is blocked, ``+86755`` is
translated and ``+86138`` is forwarded, so the facts asserted here are the ones
the plan already states.

The rest covers the purity properties of AGENT.md §5 / ADR-0002: the verdict is
a function of its arguments alone, it reads no clock, and it opens no socket.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Mapping

import pytest

from as_anti_fraud.decision import (
    REASON_RATE_LIMIT,
    RateLimit,
    decide_call,
    exceeds_limit,
    find_rate_limit,
)
from as_platform.decision.decide import (
    REASON_MATCH_BLOCK,
    REASON_MATCH_FORWARD,
    REASON_MATCH_TRANSLATE,
    REASON_NO_MATCH,
    Decision,
    DecisionAction,
    DecisionRequest,
)
from as_platform.decision.rules import Action, Rule, RuleSet

pytestmark = pytest.mark.unit

# The acceptance matrix ranges: a screened range, a forwarded range, and the
# blocked range of REQ-F-7.
_TRANSLATE_RULE_ID = "rule-75512"
_FORWARD_RULE_ID = "rule-138"
_BLOCK_RULE_ID = "rule-168"


def _rules() -> RuleSet:
    """The kernel rule set the anti-fraud use case screens after."""
    return RuleSet(
        rules=(
            Rule(
                rule_id=_TRANSLATE_RULE_ID,
                prefix="+8675512",
                action=Action.TRANSLATE,
                target="return-uas",
            ),
            Rule(
                rule_id=_FORWARD_RULE_ID,
                prefix="+86138",
                action=Action.FORWARD,
                target="core",
            ),
            Rule(rule_id=_BLOCK_RULE_ID, prefix="+86168", action=Action.BLOCK),
        )
    )


# Two calls per window. The counter is what the caller read from the store.
_RATE_LIMITS: tuple[RateLimit, ...] = (
    RateLimit(rule_id="rate-755", prefix="+86755", window_seconds=60, max_calls=2),
    RateLimit(rule_id="rate-138", prefix="+86138", window_seconds=60, max_calls=2),
)


def _request(called_number: str, received_at: float = 1000.0) -> DecisionRequest:
    return DecisionRequest(
        call_id="call-1",
        calling_number="+86216180001",
        called_number=called_number,
        received_at=received_at,
    )


def test_find_rate_limit_prefers_the_longest_prefix() -> None:
    """Longest-prefix-first, the same winner rule the kernel matching uses."""
    short = RateLimit(rule_id="short", prefix="+86755", window_seconds=60, max_calls=2)
    long = RateLimit(rule_id="long", prefix="+8675512", window_seconds=60, max_calls=5)

    found = find_rate_limit("+8675512345678", (short, long))

    assert found is not None
    assert found.rule_id == "long"


def test_find_rate_limit_matches_a_separated_number() -> None:
    """Separators carry no routing meaning, so the window still applies."""
    found = find_rate_limit("+86-755-1234-5678", _RATE_LIMITS)

    assert found is not None
    assert found.rule_id == "rate-755"


def test_find_rate_limit_returns_none_without_a_match() -> None:
    """No prefix matches, so no window governs this number."""
    assert find_rate_limit("+869990000000", _RATE_LIMITS) is None


def test_exceeds_limit_on_the_max_calls_call() -> None:
    """The max_calls-th call is itself inside the window, so it is refused."""
    limit = RateLimit(rule_id="rate-755", prefix="+86755", window_seconds=60, max_calls=3)

    assert exceeds_limit(3, limit) is True


def test_exceeds_limit_one_call_below_max_calls() -> None:
    """One call short of the window's allowance is still allowed through."""
    limit = RateLimit(rule_id="rate-755", prefix="+86755", window_seconds=60, max_calls=3)

    assert exceeds_limit(2, limit) is False


def test_decide_call_keeps_a_kernel_decline() -> None:
    """A blocked range outranks the rate screen: DECLINE stays MATCH_BLOCK."""
    decision = decide_call(_request("+861681000000"), _rules(), {}, _RATE_LIMITS)

    assert decision.action is DecisionAction.DECLINE
    assert decision.target is None
    assert decision.reason_code == REASON_MATCH_BLOCK
    assert decision.matched_rule_id == _BLOCK_RULE_ID


def test_decide_call_does_not_screen_a_call_outside_every_range() -> None:
    """NOT_FOUND is the kernel's answer; a full window cannot change it."""
    counters: Mapping[str, int] = {"rate-755": 999, "rate-138": 999}

    decision = decide_call(_request("+869990000000"), _rules(), counters, _RATE_LIMITS)

    assert decision.action is DecisionAction.NOT_FOUND
    assert decision.target is None
    assert decision.reason_code == REASON_NO_MATCH
    assert decision.matched_rule_id is None


def test_decide_call_forwards_when_the_window_is_not_full() -> None:
    """A forward hit under the limit passes through as the kernel decided."""
    counters: Mapping[str, int] = {"rate-138": 1}

    decision = decide_call(_request("+8613800138000"), _rules(), counters, _RATE_LIMITS)

    assert decision.action is DecisionAction.FORWARD
    assert decision.target == "core"
    assert decision.reason_code == REASON_MATCH_FORWARD
    assert decision.matched_rule_id == _FORWARD_RULE_ID


def test_decide_call_declines_a_forward_hit_over_the_limit() -> None:
    """A forward hit that spent its window is declined as RATE_LIMIT."""
    counters: Mapping[str, int] = {"rate-138": 2}

    decision = decide_call(_request("+8613800138000"), _rules(), counters, _RATE_LIMITS)

    assert decision.action is DecisionAction.DECLINE
    assert decision.target is None
    assert decision.reason_code == REASON_RATE_LIMIT
    assert decision.matched_rule_id == "rate-138"


def test_decide_call_declines_a_translate_hit_over_the_limit() -> None:
    """A translate hit that spent its window is declined, target dropped."""
    counters: Mapping[str, int] = {"rate-755": 2}

    decision = decide_call(_request("+8675512345678"), _rules(), counters, _RATE_LIMITS)

    assert decision.action is DecisionAction.DECLINE
    assert decision.target is None
    assert decision.reason_code == REASON_RATE_LIMIT
    assert decision.matched_rule_id == "rate-755"


def test_decide_call_does_not_rewrite_a_translate_target() -> None:
    """Rewriting the number is the translation use case's job, not this one's."""
    counters: Mapping[str, int] = {"rate-755": 1}

    decision = decide_call(_request("+8675512345678"), _rules(), counters, _RATE_LIMITS)

    assert decision.action is DecisionAction.TRANSLATE
    assert decision.target == "return-uas"
    assert decision.reason_code == REASON_MATCH_TRANSLATE
    assert decision.matched_rule_id == _TRANSLATE_RULE_ID


def test_decide_call_is_pure() -> None:
    """The same arguments produce the same decision, twice."""
    request = _request("+8613800138000")
    counters: Mapping[str, int] = {"rate-138": 2}

    first: Decision = decide_call(request, _rules(), counters, _RATE_LIMITS)
    second: Decision = decide_call(request, _rules(), counters, _RATE_LIMITS)

    assert first == second


def test_decide_call_leaves_the_counters_untouched() -> None:
    """Counting is the caller's job; the module only reads the counters."""
    counters = {"rate-138": 1}

    decide_call(_request("+8613800138000"), _rules(), counters, _RATE_LIMITS)

    assert counters == {"rate-138": 1}


def test_decide_call_reads_no_clock_and_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """received_at is injected by the caller; the module reads no time and no IO."""
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

    counters: Mapping[str, int] = {"rate-755": 2}
    decide_call(_request("+8675512345678"), _rules(), counters, _RATE_LIMITS)

    assert clock_reads == []
    assert sockets == []
