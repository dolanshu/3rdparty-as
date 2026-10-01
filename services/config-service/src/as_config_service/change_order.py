"""The change order state machine: the only write path to a configuration version.

ADR-0006 puts configuration in a PostgreSQL version repository, behind a change
order state machine, instead of GitOps: an operator must not have to learn Git to
change a number range, and a change must be versionable, traceable, staged and
rollback-capable (REQ-NF-10). Every version row in that repository was written by
one change order that walked this machine to APPLIED, so no version exists
without a recorded submitter and approver (REQ-F-14).

This module is **pure**: no socket, no clock, no global state (AGENT.md §5).
Time is a parameter of every transition, injected by the caller, which is what
makes the audit trail reproducible instead of merely recorded.

The machine:

```text
DRAFT        --submit-->             SUBMITTED
SUBMITTED    --approve-->            APPROVED
SUBMITTED    --reject-->             REJECTED
APPROVED     --begin_distribution--> DISTRIBUTING
DISTRIBUTING --mark_applied-->       APPLIED
DISTRIBUTING --roll_back-->          ROLLED_BACK
APPLIED      --roll_back-->          ROLLED_BACK
```

REJECTED, APPLIED and ROLLED_BACK are terminal: the order is over, and moving it
again would falsify the audit trail that ADR-0006 exists to produce.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace
from enum import Enum

from as_config_service.managed_rule import ManagedRule
from as_platform.api.contract import ConfigBundle

ACTION_SUBMIT = "submit"
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"
ACTION_BEGIN_DISTRIBUTION = "begin_distribution"
ACTION_MARK_APPLIED = "mark_applied"
ACTION_ROLL_BACK = "roll_back"


class ChangeState(Enum):
    """The states a change order can be in. See ADR-0006."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    DISTRIBUTING = "distributing"
    APPLIED = "applied"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class ManagedRuleChangeAction(Enum):
    """The management-plane operation proposed by a change order."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True)
class ManagedRuleChange:
    """A pending rule proposal; it does not change active ManagedRuleStore state."""

    action: ManagedRuleChangeAction
    rule_id: str
    proposed_rule: ManagedRule | None
    expected_revision: int | None

    def __post_init__(self) -> None:
        """Enforce action-specific rule shape and optimistic revision semantics."""
        if type(self.action) is not ManagedRuleChangeAction:
            raise TypeError("action must be a ManagedRuleChangeAction")
        if type(self.rule_id) is not str:
            raise TypeError("rule_id must be a string")
        if not self.rule_id.strip():
            raise ValueError("rule_id must not be blank")
        rejected_categories = {"Cc", "Cf", "Cs", "Zl", "Zp"}
        if any(
            unicodedata.category(character) in rejected_categories for character in self.rule_id
        ):
            raise ValueError("rule_id contains prohibited Unicode characters")

        if self.action is ManagedRuleChangeAction.CREATE:
            if self.expected_revision is not None:
                raise ValueError("CREATE requires expected_revision to be None")
        elif type(self.expected_revision) is not int or self.expected_revision < 1:
            raise ValueError("UPDATE and DELETE require a positive integer expected_revision")

        if self.action is ManagedRuleChangeAction.DELETE:
            if self.proposed_rule is not None:
                raise ValueError("DELETE requires proposed_rule to be None")
        elif type(self.proposed_rule) is not ManagedRule:
            raise TypeError("CREATE and UPDATE require a ManagedRule proposed_rule")

        if self.proposed_rule is not None and self.proposed_rule.rule_id != self.rule_id:
            raise ValueError("proposed_rule.rule_id must match rule_id")


# The seven edges of the ADR-0006 machine, and nothing else. See ADR-0006.
_ALLOWED_TRANSITIONS: frozenset[tuple[ChangeState, ChangeState]] = frozenset(
    {
        (ChangeState.DRAFT, ChangeState.SUBMITTED),
        (ChangeState.SUBMITTED, ChangeState.APPROVED),
        (ChangeState.SUBMITTED, ChangeState.REJECTED),
        (ChangeState.APPROVED, ChangeState.DISTRIBUTING),
        (ChangeState.DISTRIBUTING, ChangeState.APPLIED),
        (ChangeState.DISTRIBUTING, ChangeState.ROLLED_BACK),
        (ChangeState.APPLIED, ChangeState.ROLLED_BACK),
    }
)

# The states after which a change order is over. See ADR-0006.
_TERMINAL_STATES: frozenset[ChangeState] = frozenset(
    {
        ChangeState.APPLIED,
        ChangeState.REJECTED,
        ChangeState.ROLLED_BACK,
    }
)


class IllegalTransitionError(Exception):
    """Raised when a change order is asked to move along an edge the machine has not.

    Attributes:
        current: The state the order is in.
        target: The state it was asked to move to.
    """

    def __init__(self, current: ChangeState, target: ChangeState) -> None:
        """Build the error naming both ends of the refused move.

        Args:
            current: The state the order is in.
            target: The state it was asked to move to.
        """
        super().__init__(f"illegal change order transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


@dataclass(frozen=True)
class AuditEntry:
    """One append-only line of the audit trail. See ADR-0006.

    Attributes:
        actor: Who performed the action.
        action: What was done, for example ``approve``.
        at: When it was done, **injected by the caller**; this module reads no
            clock (AGENT.md §5).
    """

    actor: str
    action: str
    at: float


@dataclass(frozen=True)
class ChangeOrder:
    """One request to change the configuration, and the trail it leaves.

    Attributes:
        change_id: Stable identifier of the change order.
        state: Where the order is in the ADR-0006 machine.
        bundle: The unchanged runtime configuration carried into the version repository.
        managed_rule_change: Optional management-plane proposal, separate from runtime bundle
            and active managed-rule state.
        created_by: Who submitted the order.
        created_at: When the order was created, injected by the caller.
        approver: Who approved it; ``None`` until ``approve`` runs. REQ-F-14.
        approved_at: When it was approved, injected by the caller. REQ-F-14.
        audit: The append-only trail, oldest first.
    """

    change_id: str
    state: ChangeState
    bundle: ConfigBundle
    created_by: str
    created_at: float
    approver: str | None = None
    approved_at: float | None = None
    audit: tuple[AuditEntry, ...] = ()
    managed_rule_change: ManagedRuleChange | None = None

    def __post_init__(self) -> None:
        """Keep an embedded proposal inside the typed management-plane boundary."""
        if (
            self.managed_rule_change is not None
            and type(self.managed_rule_change) is not ManagedRuleChange
        ):
            raise TypeError("managed_rule_change must be a ManagedRuleChange or None")


def is_terminal(state: ChangeState) -> bool:
    """Whether a change order in ``state`` is finished.

    Args:
        state: The state to test.

    Returns:
        ``True`` for APPLIED, REJECTED and ROLLED_BACK.
    """
    return state in _TERMINAL_STATES


def _guard(order: ChangeOrder, target: ChangeState) -> None:
    """Refuse any move that is not an edge of the ADR-0006 machine.

    Args:
        order: The change order being moved.
        target: The state it is asked to move to.

    Raises:
        IllegalTransitionError: If ``order.state -> target`` is not allowed.
    """
    if (order.state, target) not in _ALLOWED_TRANSITIONS:
        raise IllegalTransitionError(order.state, target)


def _appended(order: ChangeOrder, actor: str, action: str, now: float) -> tuple[AuditEntry, ...]:
    """The audit trail of ``order`` plus one entry.

    Args:
        order: The change order being moved.
        actor: Who performed the action.
        action: What was done.
        now: When, injected by the caller.

    Returns:
        A new tuple; the existing entries are never rewritten.
    """
    return (*order.audit, AuditEntry(actor=actor, action=action, at=now))


def _reasoned(action: str, reason: str) -> str:
    """The audit action of a transition that carries a reason.

    Args:
        action: The action name, for example ``reject``.
        reason: Why it was done; it travels with the audit line so the trail can
            be read without a second table. See ADR-0006.

    Returns:
        The audit action string, for example ``reject: prefix clash``.
    """
    return f"{action}: {reason}"


def submit(order: ChangeOrder, actor: str, now: float) -> ChangeOrder:
    """Hand a DRAFT order in for approval: DRAFT → SUBMITTED.

    Args:
        order: The change order to submit.
        actor: Who submits it.
        now: When, injected by the caller.

    Returns:
        A new order in SUBMITTED, with one more audit entry.

    Raises:
        IllegalTransitionError: If the order is not in DRAFT.
    """
    _guard(order, ChangeState.SUBMITTED)
    return replace(
        order,
        state=ChangeState.SUBMITTED,
        audit=_appended(order, actor, ACTION_SUBMIT, now),
    )


def approve(order: ChangeOrder, actor: str, now: float) -> ChangeOrder:
    """Approve a submitted order: SUBMITTED → APPROVED.

    The approver and the approval time are written into the order itself, not
    only into the audit trail: REQ-F-14 asks for an approval record with a
    responsible person and a timestamp, and an approval without either is not
    the thing the requirement asks for. See ADR-0006.

    Args:
        order: The change order to approve.
        actor: Who approves it; recorded as the approver.
        now: When, injected by the caller; recorded as the approval time.

    Returns:
        A new order in APPROVED carrying ``approver`` and ``approved_at``.

    Raises:
        IllegalTransitionError: If the order is not in SUBMITTED.
    """
    _guard(order, ChangeState.APPROVED)
    return replace(
        order,
        state=ChangeState.APPROVED,
        approver=actor,
        approved_at=now,
        audit=_appended(order, actor, ACTION_APPROVE, now),
    )


def reject(order: ChangeOrder, actor: str, reason: str, now: float) -> ChangeOrder:
    """Reject a submitted order: SUBMITTED → REJECTED.

    Args:
        order: The change order to reject.
        actor: Who rejects it.
        reason: Why; kept in the audit trail.
        now: When, injected by the caller.

    Returns:
        A new order in the terminal state REJECTED.

    Raises:
        IllegalTransitionError: If the order is not in SUBMITTED.
    """
    if not reason.strip():
        raise ValueError("rejection reason must not be blank")
    _guard(order, ChangeState.REJECTED)
    return replace(
        order,
        state=ChangeState.REJECTED,
        audit=_appended(order, actor, _reasoned(ACTION_REJECT, reason), now),
    )


def begin_distribution(order: ChangeOrder, actor: str, now: float) -> ChangeOrder:
    """Start staged distribution of an approved order: APPROVED → DISTRIBUTING.

    Args:
        order: The approved change order.
        actor: Who starts the distribution.
        now: When, injected by the caller.

    Returns:
        A new order in DISTRIBUTING.

    Raises:
        IllegalTransitionError: If the order is not in APPROVED.
    """
    _guard(order, ChangeState.DISTRIBUTING)
    return replace(
        order,
        state=ChangeState.DISTRIBUTING,
        audit=_appended(order, actor, ACTION_BEGIN_DISTRIBUTION, now),
    )


def mark_applied(order: ChangeOrder, actor: str, now: float) -> ChangeOrder:
    """Record that the fleet has loaded the version: DISTRIBUTING → APPLIED.

    Args:
        order: The change order being distributed.
        actor: Who confirms the rollout.
        now: When, injected by the caller.

    Returns:
        A new order in the terminal state APPLIED.

    Raises:
        IllegalTransitionError: If the order is not in DISTRIBUTING.
    """
    _guard(order, ChangeState.APPLIED)
    return replace(
        order,
        state=ChangeState.APPLIED,
        audit=_appended(order, actor, ACTION_MARK_APPLIED, now),
    )


def roll_back(order: ChangeOrder, actor: str, reason: str, now: float) -> ChangeOrder:
    """Roll a distributing or applied order back: APPLIED | DISTRIBUTING → ROLLED_BACK.

    A failing health check during distribution rolls back as well as a
    regression found after the fact; both are the same transition, because in
    both cases the remedy is to move the effective marker back one immutable
    version row. See ADR-0006.

    Args:
        order: The change order to roll back.
        actor: Who rolls it back.
        reason: Why; kept in the audit trail.
        now: When, injected by the caller.

    Returns:
        A new order in the terminal state ROLLED_BACK.

    Raises:
        IllegalTransitionError: If the order is neither APPLIED nor DISTRIBUTING.
    """
    if not reason.strip():
        raise ValueError("rollback reason must not be blank")
    _guard(order, ChangeState.ROLLED_BACK)
    return replace(
        order,
        state=ChangeState.ROLLED_BACK,
        audit=_appended(order, actor, _reasoned(ACTION_ROLL_BACK, reason), now),
    )
