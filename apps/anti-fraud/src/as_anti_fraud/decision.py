"""The anti-fraud use case's decision: the kernel verdict plus a rate screen.

This module does **not** judge a call. Judging is the kernel's job
(``as_platform.decision.decide.decide``); this module only answers the one
question the kernel deliberately leaves open: of the calls the kernel would let
through, which ones has this caller already spent? Everything else passes through
untouched, so a ``DECLINE`` can never be screened into a route and a
``NOT_FOUND`` stays a 404 (REQ-F-6, REQ-F-7).

The rate window itself is **not** here. Counting lives in the state store, which
means it lives outside the process: a replica that can be killed at any moment
must not hold a caller's window in memory (ADR-0002). The caller reads the
counter and injects it as ``counters``, and ``window_seconds`` is carried on the
rule for the caller's benefit only — this module never reads a clock, opens no
socket and keeps no global state, so the verdict is a function of its arguments
alone (AGENT.md §5). See ADR-0002.

Nor does this module rewrite a number. The kernel's ``TRANSLATE`` target belongs
to the translation use case; anti-fraud only decides whether the call may go out
at all, and a call it declines carries no target.

No SIP concepts appear here: the verdict arrives as a ``DecisionRequest`` and
leaves as a ``Decision``. What the adaptation layer makes of it — 603 Decline
here, ``608 Rejected`` for the screening answer of RFC 8688 — is the adapter's
concern, not this module's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from as_platform.decision.decide import (
    Decision,
    DecisionAction,
    DecisionRequest,
    decide,
)
from as_platform.decision.rules import RuleSet, normalize_number

# Distinct from the kernel's MATCH_BLOCK: the kernel refuses a number range,
# this module refuses a caller that has spent its window. Keeping the two apart
# is what lets an operator tell a blocked destination from a throttled caller.
REASON_RATE_LIMIT = "RATE_LIMIT"


@dataclass(frozen=True)
class RateLimit:
    """One rate window: which range it guards and how many calls it allows.

    Attributes:
        rule_id: Stable identifier. It is also the key the caller counts under,
            so the counter injected as ``counters`` is addressed by it.
        prefix: The number range this window applies to, in normalized form.
        window_seconds: The length of the window. The caller owns the counting
            and the expiry; this module never reads a clock. See ADR-0002.
        max_calls: How many calls one window allows.
    """

    rule_id: str
    prefix: str
    window_seconds: int
    max_calls: int


def find_rate_limit(number: str, limits: tuple[RateLimit, ...]) -> RateLimit | None:
    """Select the rate window governing a number.

    Longest-prefix-first, which is the same winner rule the kernel's rule
    matching uses (REQ-F-6): a narrow range beats the wider range containing it.

    Args:
        number: The number to find a window for; normalized before matching.
        limits: The candidate rate windows.

    Returns:
        The window with the longest matching prefix, or ``None`` when none
        matches, meaning the number is not rate screened at all.
    """
    normalized = normalize_number(number)

    candidates = [
        (len(normalize_number(limit.prefix)), limit)
        for limit in limits
        if normalized.startswith(normalize_number(limit.prefix))
    ]
    if not candidates:
        return None

    return max(candidates, key=lambda candidate: candidate[0])[1]


def exceeds_limit(calls_in_window: int, limit: RateLimit) -> bool:
    """Tell whether a counter has spent its window.

    The comparison is ``>=`` and not ``>``: the ``max_calls``-th call is itself
    inside the window, so allowing it would let ``max_calls + 1`` calls through
    before the window is full.

    Args:
        calls_in_window: Calls already counted in this window, injected by the
            caller from the state store.
        limit: The window to compare against.

    Returns:
        ``True`` when the counter has reached the window's allowance.
    """
    return calls_in_window >= limit.max_calls


def decide_call(
    request: DecisionRequest,
    rules: RuleSet,
    counters: Mapping[str, int],
    limits: tuple[RateLimit, ...],
) -> Decision:
    """Decide one call: the kernel's verdict, screened against a rate window.

    ``DECLINE`` and ``NOT_FOUND`` are the kernel's answers and are returned
    unchanged — a blocked range outranks any rate window (REQ-F-7) and a number
    outside every range is not this use case's business (REQ-F-6), so a full
    window can never overturn either. Only ``FORWARD`` and ``TRANSLATE`` are
    screened: when the winning window for the called number has been spent, the
    call is declined with ``RATE_LIMIT`` and no target. Otherwise the kernel's
    verdict passes through untouched, target included — this use case screens, it
    does not translate.

    The screen is deliberately the last step: whoever can inject calls into the
    AS can otherwise spend a window on a number that would have been refused
    anyway. See ADR-0016.

    Args:
        request: The request to decide; the caller injects ``received_at``.
        rules: The kernel rule set of the current configuration version.
        counters: Calls counted per ``RateLimit.rule_id``, read-only here.
        limits: The rate windows available to screen the call.

    Returns:
        A decision. ``DECLINE`` answers 603 (REQ-F-7) and ``NOT_FOUND`` answers
        404 (REQ-F-6); neither creates an outbound leg.
    """
    verdict = decide(request, rules)

    # The kernel's refusals are final. See REQ-F-6 and REQ-F-7.
    if verdict.action not in (DecisionAction.FORWARD, DecisionAction.TRANSLATE):
        return verdict

    limit = find_rate_limit(request.called_number, limits)
    if limit is None or not exceeds_limit(counters.get(limit.rule_id, 0), limit):
        return verdict

    # 603 Decline; the call is not routed and its number is not rewritten.
    return Decision(
        action=DecisionAction.DECLINE,
        target=None,
        reason_code=REASON_RATE_LIMIT,
        matched_rule_id=limit.rule_id,
    )
