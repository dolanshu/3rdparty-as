"""The decide() seam: a pure function from a request and a rule set to a decision.

``decide()`` is the whole routing policy of the kernel. It is pure on purpose:
no socket, no clock, no global state, no IO (AGENT.md §5, ADR-0002). The time a
request arrived is an **argument**, never something this module reads — a hidden
clock read would turn ``decide()`` into a function of time and make both its
idempotence and its tests impossible to state.

Writing the resulting call state and emitting telemetry is the caller's job
(hld.md §5 steps 5 and 6), not this function's.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .rules import Action, RuleSet, normalize_number


class DecisionAction(Enum):
    """The four outcomes of hld.md §5 step 4."""

    FORWARD = "forward"
    TRANSLATE = "translate"
    DECLINE = "decline"
    NOT_FOUND = "not_found"


REASON_MATCH_FORWARD = "MATCH_FORWARD"
REASON_MATCH_TRANSLATE = "MATCH_TRANSLATE"
REASON_MATCH_BLOCK = "MATCH_BLOCK"
REASON_NO_MATCH = "NO_MATCH"


@dataclass(frozen=True)
class DecisionRequest:
    """What the kernel sees of a request; it carries no SIP concepts.

    Attributes:
        call_id: The Call-ID, used for state keys and traces.
        calling_number: The calling party number.
        called_number: The called party number; this is what rules match on.
        received_at: When the request arrived, **injected by the caller**. This
            module never reads a clock; see ADR-0002.
    """

    call_id: str
    calling_number: str
    called_number: str
    received_at: float


@dataclass(frozen=True)
class Decision:
    """The single output of decide().

    Attributes:
        action: What the adaptation layer must do.
        target: Where to route the call, ``None`` for DECLINE and NOT_FOUND.
        reason_code: Why, for traces and the console.
        matched_rule_id: The rule that decided, ``None`` when none matched.
    """

    action: DecisionAction
    target: str | None
    reason_code: str
    matched_rule_id: str | None


def decide(request: DecisionRequest, rules: RuleSet) -> Decision:
    """Evaluate one request against one rule set.

    Args:
        request: The request to evaluate.
        rules: The rule set of the currently loaded configuration version.

    Returns:
        A decision. ``DECLINE`` answers 603 (REQ-F-7) and ``NOT_FOUND`` answers
        404 (REQ-F-6); neither creates an outbound leg.
    """
    called = normalize_number(request.called_number)
    rule = rules.match(called)

    if rule is None:
        return Decision(
            action=DecisionAction.NOT_FOUND,
            target=None,
            reason_code=REASON_NO_MATCH,
            matched_rule_id=None,
        )

    if rule.action is Action.BLOCK:
        # 603 Decline; never route a blocked call. See REQ-F-7.
        return Decision(
            action=DecisionAction.DECLINE,
            target=None,
            reason_code=REASON_MATCH_BLOCK,
            matched_rule_id=rule.rule_id,
        )

    if rule.action is Action.TRANSLATE:
        return Decision(
            action=DecisionAction.TRANSLATE,
            target=rule.target,
            reason_code=REASON_MATCH_TRANSLATE,
            matched_rule_id=rule.rule_id,
        )

    # Forward: the rule target if it names one, otherwise the number as called.
    return Decision(
        action=DecisionAction.FORWARD,
        target=rule.target if rule.target is not None else called,
        reason_code=REASON_MATCH_FORWARD,
        matched_rule_id=rule.rule_id,
    )
