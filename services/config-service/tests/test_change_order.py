"""Unit tests for the ADR-0006 change order state machine.

REQ-F-14 (approval flow: the approver and the approval time must be persisted),
REQ-NF-10 (a configuration change must be versionable, traceable, staged and
rollback-capable) and AGENT.md §5: this module is pure — no clock, no socket,
no global state. Every timestamp below is injected by the test.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from functools import partial

import pytest

from as_config_service.change_order import (
    AuditEntry,
    ChangeOrder,
    ChangeState,
    IllegalTransitionError,
    ManagedRuleChange,
    ManagedRuleChangeAction,
    approve,
    begin_distribution,
    is_terminal,
    mark_applied,
    reject,
    roll_back,
    submit,
)
from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService
from as_platform.api.contract import ConfigBundle, RuleDTO

pytestmark = pytest.mark.unit

CREATED_AT = 1_700_000_000.0
ACTOR = "ops-alice"
APPROVER = "mgr-bob"


def _bundle(version: str = "v1") -> ConfigBundle:
    """A one-rule configuration bundle as it crosses the internal API."""
    return ConfigBundle(
        version=version,
        rules=(
            RuleDTO(
                rule_id="rule-755",
                prefix="+86755",
                action="translate",
                target="return-uas",
            ),
        ),
    )


def _order() -> ChangeOrder:
    """A fresh DRAFT change order."""
    return ChangeOrder(
        change_id="co-1",
        state=ChangeState.DRAFT,
        bundle=_bundle(),
        created_by=ACTOR,
        created_at=CREATED_AT,
    )


def _managed_rule(rule_id: str = "managed-1") -> ManagedRule:
    return ManagedRule(
        rule_id=rule_id,
        name="International callers",
        match_field=MatchField.CALLING,
        match_mode=MatchMode.PREFIX,
        match_value="+8613",
        target_service=TargetService.TRANSLATION,
        enabled=True,
    )


@pytest.mark.parametrize(
    ("action", "proposed_rule", "expected_revision"),
    [
        (ManagedRuleChangeAction.CREATE, _managed_rule(), None),
        (ManagedRuleChangeAction.UPDATE, _managed_rule(), 3),
        (ManagedRuleChangeAction.DELETE, None, 3),
    ],
)
def test_managed_rule_change_accepts_valid_action_shapes(
    action: ManagedRuleChangeAction,
    proposed_rule: ManagedRule | None,
    expected_revision: int | None,
) -> None:
    change = ManagedRuleChange(action, "managed-1", proposed_rule, expected_revision)

    assert change.action is action
    assert change.rule_id == "managed-1"
    assert change.proposed_rule == proposed_rule
    assert change.expected_revision == expected_revision


@pytest.mark.parametrize(
    ("action", "rule_id", "proposed_rule", "expected_revision", "error"),
    [
        ("create", "managed-1", _managed_rule(), None, TypeError),
        (ManagedRuleChangeAction.CREATE, 1, _managed_rule(), None, TypeError),
        (ManagedRuleChangeAction.CREATE, " ", _managed_rule(), None, ValueError),
        (ManagedRuleChangeAction.CREATE, "managed\u200b1", _managed_rule(), None, ValueError),
        (ManagedRuleChangeAction.CREATE, "managed-1", _managed_rule("other"), None, ValueError),
        (ManagedRuleChangeAction.CREATE, "managed-1", _managed_rule(), 1, ValueError),
        (ManagedRuleChangeAction.CREATE, "managed-1", None, None, TypeError),
        (ManagedRuleChangeAction.UPDATE, "managed-1", _managed_rule(), None, ValueError),
        (ManagedRuleChangeAction.UPDATE, "managed-1", _managed_rule(), 0, ValueError),
        (ManagedRuleChangeAction.UPDATE, "managed-1", _managed_rule(), True, ValueError),
        (ManagedRuleChangeAction.UPDATE, "managed-1", None, 1, TypeError),
        (ManagedRuleChangeAction.DELETE, "managed-1", None, None, ValueError),
        (ManagedRuleChangeAction.DELETE, "managed-1", None, 0, ValueError),
        (ManagedRuleChangeAction.DELETE, "managed-1", None, True, ValueError),
        (ManagedRuleChangeAction.DELETE, "managed-1", _managed_rule(), 1, ValueError),
    ],
)
def test_managed_rule_change_rejects_invalid_action_shapes(
    action: object,
    rule_id: object,
    proposed_rule: object,
    expected_revision: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        ManagedRuleChange(action, rule_id, proposed_rule, expected_revision)  # type: ignore[arg-type]


def test_change_order_rejects_untyped_managed_rule_change() -> None:
    with pytest.raises(TypeError, match="ManagedRuleChange or None"):
        ChangeOrder(
            change_id="co-1",
            state=ChangeState.DRAFT,
            bundle=_bundle(),
            created_by=ACTOR,
            created_at=CREATED_AT,
            managed_rule_change=object(),  # type: ignore[arg-type]
        )


def _order_in(state: ChangeState) -> ChangeOrder:
    """Walk the legal path from DRAFT to ``state``, each step one second apart."""
    order = _order()
    if state is ChangeState.DRAFT:
        return order
    if state is ChangeState.SUBMITTED:
        return submit(order, ACTOR, CREATED_AT + 1.0)
    if state is ChangeState.APPROVED:
        return approve(submit(order, ACTOR, CREATED_AT + 1.0), APPROVER, CREATED_AT + 2.0)
    if state is ChangeState.DISTRIBUTING:
        return begin_distribution(
            approve(submit(order, ACTOR, CREATED_AT + 1.0), APPROVER, CREATED_AT + 2.0),
            ACTOR,
            CREATED_AT + 3.0,
        )
    if state is ChangeState.APPLIED:
        return mark_applied(
            begin_distribution(
                approve(submit(order, ACTOR, CREATED_AT + 1.0), APPROVER, CREATED_AT + 2.0),
                ACTOR,
                CREATED_AT + 3.0,
            ),
            ACTOR,
            CREATED_AT + 4.0,
        )
    if state is ChangeState.REJECTED:
        submitted = submit(order, ACTOR, CREATED_AT + 1.0)
        return reject(submitted, APPROVER, "prefix clash", CREATED_AT + 2.0)
    if state is ChangeState.ROLLED_BACK:
        return roll_back(
            mark_applied(
                begin_distribution(
                    approve(submit(order, ACTOR, CREATED_AT + 1.0), APPROVER, CREATED_AT + 2.0),
                    ACTOR,
                    CREATED_AT + 3.0,
                ),
                ACTOR,
                CREATED_AT + 4.0,
            ),
            ACTOR,
            "health check failed",
            CREATED_AT + 5.0,
        )
    raise AssertionError(f"no legal path to {state}")


# One illegal move per origin state: the call that must be refused.
_ILLEGAL_MOVES: dict[str, Callable[[ChangeOrder], ChangeOrder]] = {
    "submit": partial(submit, actor=ACTOR, now=CREATED_AT + 9.0),
    "approve": partial(approve, actor=APPROVER, now=CREATED_AT + 9.0),
    "begin_distribution": partial(begin_distribution, actor=ACTOR, now=CREATED_AT + 9.0),
    "mark_applied": partial(mark_applied, actor=ACTOR, now=CREATED_AT + 9.0),
}


def test_happy_path_appends_one_audit_entry_per_step() -> None:
    """DRAFT → SUBMITTED → APPROVED → DISTRIBUTING → APPLIED, one audit entry each. REQ-F-14."""
    draft = _order()
    assert draft.audit == ()

    submitted = submit(draft, ACTOR, CREATED_AT + 1.0)
    assert submitted.state is ChangeState.SUBMITTED
    assert len(submitted.audit) == 1

    approved = approve(submitted, APPROVER, CREATED_AT + 2.0)
    assert approved.state is ChangeState.APPROVED
    assert len(approved.audit) == 2

    distributing = begin_distribution(approved, ACTOR, CREATED_AT + 3.0)
    assert distributing.state is ChangeState.DISTRIBUTING
    assert len(distributing.audit) == 3

    applied = mark_applied(distributing, ACTOR, CREATED_AT + 4.0)
    assert applied.state is ChangeState.APPLIED
    assert len(applied.audit) == 4

    assert applied.change_id == draft.change_id
    assert applied.bundle is draft.bundle
    assert [entry.action for entry in applied.audit] == [
        "submit",
        "approve",
        "begin_distribution",
        "mark_applied",
    ]
    assert [entry.at for entry in applied.audit] == [
        CREATED_AT + 1.0,
        CREATED_AT + 2.0,
        CREATED_AT + 3.0,
        CREATED_AT + 4.0,
    ]


def test_approve_persists_approver_and_approved_at() -> None:
    """An approval without an approver and a time is not an approval. REQ-F-14."""
    submitted = submit(_order(), ACTOR, CREATED_AT + 1.0)
    assert submitted.approver is None
    assert submitted.approved_at is None

    approved = approve(submitted, APPROVER, CREATED_AT + 2.0)

    assert approved.approver == APPROVER
    assert approved.approved_at == CREATED_AT + 2.0
    assert approved.audit[-1] == AuditEntry(actor=APPROVER, action="approve", at=CREATED_AT + 2.0)


def test_draft_cannot_jump_straight_to_applied() -> None:
    """There is no bypass: an unapproved change never reaches APPLIED. REQ-F-14."""
    with pytest.raises(IllegalTransitionError) as caught:
        mark_applied(_order(), ACTOR, CREATED_AT + 1.0)

    message = str(caught.value)
    assert ChangeState.DRAFT.value in message
    assert ChangeState.APPLIED.value in message


@pytest.mark.parametrize(
    ("origin", "move"),
    [
        (ChangeState.APPLIED, "approve"),
        (ChangeState.APPLIED, "begin_distribution"),
        (ChangeState.REJECTED, "submit"),
        (ChangeState.REJECTED, "approve"),
        (ChangeState.ROLLED_BACK, "submit"),
        (ChangeState.DRAFT, "approve"),
        (ChangeState.DRAFT, "begin_distribution"),
        (ChangeState.SUBMITTED, "begin_distribution"),
        (ChangeState.SUBMITTED, "mark_applied"),
        (ChangeState.APPROVED, "mark_applied"),
        (ChangeState.DISTRIBUTING, "approve"),
    ],
)
def test_illegal_transition_raises(origin: ChangeState, move: str) -> None:
    """Only the seven edges of ADR-0006 move a change order; everything else is refused."""
    order = _order_in(origin)

    with pytest.raises(IllegalTransitionError) as caught:
        _ILLEGAL_MOVES[move](order)

    message = str(caught.value)
    assert origin.value in message


def test_reject_is_terminal_and_carries_its_reason() -> None:
    """SUBMITTED → REJECTED ends the order; the reason survives in the audit trail."""
    submitted = submit(_order(), ACTOR, CREATED_AT + 1.0)
    rejected = reject(submitted, APPROVER, "prefix clash", CREATED_AT + 2.0)

    assert rejected.state is ChangeState.REJECTED
    assert is_terminal(rejected.state)
    assert rejected.approver is None, "a rejection is not an approval; no approver is recorded"
    assert "reject" in rejected.audit[-1].action
    assert "prefix clash" in rejected.audit[-1].action
    assert rejected.audit[-1].actor == APPROVER
    assert rejected.audit[-1].at == CREATED_AT + 2.0


@pytest.mark.parametrize("reason", ["", " \t\n"])
def test_reject_refuses_blank_reason_without_changing_submitted_order(reason: str) -> None:
    submitted = submit(_order(), ACTOR, CREATED_AT + 1.0)

    with pytest.raises(ValueError, match="reason must not be blank"):
        reject(submitted, APPROVER, reason, CREATED_AT + 2.0)

    assert submitted.state is ChangeState.SUBMITTED
    assert len(submitted.audit) == 1


@pytest.mark.parametrize("origin", [ChangeState.APPLIED, ChangeState.DISTRIBUTING])
def test_roll_back_is_reachable_and_terminal(origin: ChangeState) -> None:
    """A roll back is possible once distribution started, and it ends the order. REQ-NF-10."""
    order = _order_in(origin)
    rolled_back = roll_back(order, ACTOR, "health check failed", CREATED_AT + 9.0)

    assert rolled_back.state is ChangeState.ROLLED_BACK
    assert is_terminal(rolled_back.state)
    assert "roll_back" in rolled_back.audit[-1].action
    assert "health check failed" in rolled_back.audit[-1].action


@pytest.mark.parametrize(
    ("origin", "reason"),
    [
        (ChangeState.APPLIED, ""),
        (ChangeState.APPLIED, " \t\n"),
        (ChangeState.DISTRIBUTING, ""),
        (ChangeState.DISTRIBUTING, " \t\n"),
    ],
)
def test_roll_back_refuses_blank_reason_without_changing_order(
    origin: ChangeState, reason: str
) -> None:
    order = _order_in(origin)

    with pytest.raises(ValueError, match="reason must not be blank"):
        roll_back(order, ACTOR, reason, CREATED_AT + 9.0)

    assert order.state is origin
    assert len(order.audit) == (4 if origin is ChangeState.APPLIED else 3)


def test_migration_leaves_the_original_order_untouched() -> None:
    """Every transition returns a new order; the input keeps state, audit and approval fields."""
    draft = _order()
    submitted = submit(draft, ACTOR, CREATED_AT + 1.0)
    approved = approve(submitted, APPROVER, CREATED_AT + 2.0)

    assert draft.state is ChangeState.DRAFT
    assert draft.audit == ()
    assert draft.approver is None
    assert draft.approved_at is None

    assert submitted.state is ChangeState.SUBMITTED
    assert len(submitted.audit) == 1
    assert submitted.approver is None
    assert submitted.approved_at is None

    assert approved is not submitted
    assert approved.approver == APPROVER


def test_state_machine_reads_no_clock_and_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Time is injected by the caller and no socket is opened. AGENT.md §5."""
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

    order = _order()
    approved = approve(submit(order, ACTOR, CREATED_AT + 1.0), APPROVER, CREATED_AT + 2.0)
    distributing = begin_distribution(approved, ACTOR, CREATED_AT + 3.0)
    applied = mark_applied(distributing, ACTOR, CREATED_AT + 4.0)
    rolled_back = roll_back(applied, ACTOR, "regression", CREATED_AT + 5.0)
    rejected = reject(submit(order, ACTOR, CREATED_AT + 1.0), APPROVER, "no", CREATED_AT + 2.0)

    assert rolled_back.state is ChangeState.ROLLED_BACK
    assert rejected.state is ChangeState.REJECTED
    assert clock_reads == []
    assert sockets == []


@pytest.mark.parametrize(
    ("state", "terminal"),
    [
        (ChangeState.DRAFT, False),
        (ChangeState.SUBMITTED, False),
        (ChangeState.APPROVED, False),
        (ChangeState.DISTRIBUTING, False),
        (ChangeState.APPLIED, True),
        (ChangeState.REJECTED, True),
        (ChangeState.ROLLED_BACK, True),
    ],
)
def test_is_terminal(state: ChangeState, terminal: bool) -> None:
    """APPLIED, REJECTED and ROLLED_BACK are the end of the line."""
    assert is_terminal(state) is terminal
