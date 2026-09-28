"""Unit tests for console authorization and audit.

REQ-S-4 assigns every console operation to two obligations: it is authorized,
and it leaves a trace. ADR-0016 assigns that requirement to the M4 control
plane and pins the constraint; ADR-0006 makes change orders the governance
loop, so the audit trail here has to line up with the approval trail there.

What is tested is the kernel only: the authorization decision and the audit
record it produces. There is no HTTP framework, no login, no session and no
password in this layer, which is what makes the decision a pure function and
the table below cheap to pin (AGENT.md §5, AGENT.md §6).
"""

from __future__ import annotations

import dataclasses
import socket
import time

import pytest

from as_console.access import (
    ROLE_PERMISSIONS,
    AuditOutcome,
    AuditRecord,
    Permission,
    Principal,
    Role,
    audit,
    authorize,
    authorize_and_audit,
    may_approve,
    permissions_for,
)

pytestmark = pytest.mark.unit

INJECTED_AT = 1_700_000_000.0

# The expected role -> permission table, owned by the test rather than derived
# from the module under test. Deriving it would make the matrix below vacuous.
EXPECTED_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.READ_CONFIG}),
    Role.OPERATOR: frozenset({Permission.READ_CONFIG, Permission.SUBMIT_CHANGE}),
    Role.APPROVER: frozenset(
        {
            Permission.READ_CONFIG,
            Permission.SUBMIT_CHANGE,
            Permission.APPROVE_CHANGE,
            Permission.ROLLBACK_CHANGE,
        }
    ),
    Role.ADMIN: frozenset(Permission),
}

MATRIX_CASES: list[tuple[Role, Permission, bool]] = [
    (role, permission, permission in granted)
    for role, granted in EXPECTED_ROLE_PERMISSIONS.items()
    for permission in Permission
]

CHANGE_RESOURCE = "change:co-7"
DENIED_FOR_A_VIEWER: tuple[Permission, ...] = tuple(
    permission for permission in Permission if permission is not Permission.READ_CONFIG
)


def _principal(user_id: str, *roles: Role) -> Principal:
    """A principal holding exactly ``roles``."""
    return Principal(user_id=user_id, roles=frozenset(roles))


@pytest.mark.parametrize(("role", "permission", "expected"), MATRIX_CASES)
def test_role_permission_matrix(role: Role, permission: Permission, expected: bool) -> None:
    """Every role against every permission, expected outcome spelled out. REQ-S-4."""
    principal = _principal("ops-1", role)

    assert authorize(principal, permission) is expected
    assert (permission in permissions_for(principal)) is expected


def test_the_matrix_covers_every_role_and_every_permission() -> None:
    """An incomplete matrix would let a hole in the table pass silently."""
    assert set(EXPECTED_ROLE_PERMISSIONS) == set(Role)
    assert len(MATRIX_CASES) == len(Role) * len(Permission)
    assert {case[1] for case in MATRIX_CASES} == set(Permission)
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_the_declared_matrix_is_the_expected_one() -> None:
    """The module's own table must agree with the table this test expects."""
    for role, granted in EXPECTED_ROLE_PERMISSIONS.items():
        assert ROLE_PERMISSIONS[role] == granted
        assert permissions_for(_principal("ops-1", role)) == granted


def test_admin_holds_every_permission() -> None:
    """ADMIN holds all of them, enumerated from the enum so adding one cannot slip past."""
    assert set(Permission) == {
        Permission.READ_CONFIG,
        Permission.SUBMIT_CHANGE,
        Permission.APPROVE_CHANGE,
        Permission.ROLLBACK_CHANGE,
        Permission.MANAGE_USERS,
    }
    assert permissions_for(_principal("root", Role.ADMIN)) == frozenset(Permission)
    assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(Permission)


@pytest.mark.parametrize("permission", list(Permission))
def test_a_principal_without_roles_is_denied_everything(permission: Permission) -> None:
    """No role grants nothing: authorization fails closed. See ADR-0016."""
    nobody = _principal("nobody")

    assert permissions_for(nobody) == frozenset()
    assert authorize(nobody, permission) is False
    assert may_approve(nobody, "someone-else") is False


def test_permissions_for_unions_every_role_the_principal_holds() -> None:
    """Roles add up; holding two grants the union of both, never the intersection."""
    viewer_and_approver = _principal("ops-1", Role.VIEWER, Role.APPROVER)
    assert permissions_for(viewer_and_approver) == frozenset(
        {
            Permission.READ_CONFIG,
            Permission.SUBMIT_CHANGE,
            Permission.APPROVE_CHANGE,
            Permission.ROLLBACK_CHANGE,
        }
    )

    viewer_and_operator = _principal("ops-2", Role.VIEWER, Role.OPERATOR)
    assert permissions_for(viewer_and_operator) == frozenset(
        {Permission.READ_CONFIG, Permission.SUBMIT_CHANGE}
    )

    operator_and_admin = _principal("ops-3", Role.OPERATOR, Role.ADMIN)
    assert permissions_for(operator_and_admin) == frozenset(Permission)


def test_the_submitter_cannot_approve_their_own_change() -> None:
    """Two-person rule: the person who submitted a change is not who approves it. ADR-0006."""
    approver = _principal("alice", Role.APPROVER)

    assert may_approve(approver, "alice") is False
    assert may_approve(approver, "bob") is True


def test_the_two_person_rule_still_needs_the_permission() -> None:
    """Being somebody else is not enough, and having the permission is not enough."""
    assert may_approve(_principal("bob", Role.APPROVER), "alice") is True
    assert may_approve(_principal("bob", Role.ADMIN), "alice") is True

    assert may_approve(_principal("bob", Role.OPERATOR), "alice") is False
    assert may_approve(_principal("bob", Role.VIEWER), "alice") is False

    # Holds APPROVE_CHANGE and is nevertheless the submitter: still denied.
    assert authorize(_principal("bob", Role.APPROVER), Permission.APPROVE_CHANGE) is True
    assert may_approve(_principal("bob", Role.APPROVER), "bob") is False


@pytest.mark.parametrize("permission", DENIED_FOR_A_VIEWER)
def test_a_denial_still_produces_an_audit_record(permission: Permission) -> None:
    """REQ-S-4 records refusals too; a denial that leaves no trace is invisible."""
    viewer = _principal("carol", Role.VIEWER)

    allowed, record = authorize_and_audit(viewer, permission, CHANGE_RESOURCE, INJECTED_AT)

    assert allowed is False
    assert record == AuditRecord(
        actor="carol",
        action=permission.value,
        resource=CHANGE_RESOURCE,
        outcome=AuditOutcome.DENIED,
        at=INJECTED_AT,
    )


def test_an_allowance_produces_an_allowed_audit_record() -> None:
    """The allowed branch carries the same fields, differing only in outcome."""
    operator = _principal("alice", Role.OPERATOR)

    allowed, record = authorize_and_audit(
        operator, Permission.SUBMIT_CHANGE, CHANGE_RESOURCE, INJECTED_AT, detail="draft"
    )

    assert allowed is True
    assert record == AuditRecord(
        actor="alice",
        action=Permission.SUBMIT_CHANGE.value,
        resource=CHANGE_RESOURCE,
        outcome=AuditOutcome.ALLOWED,
        at=INJECTED_AT,
        detail="draft",
    )


@pytest.mark.parametrize(
    ("allowed", "outcome"),
    [(True, AuditOutcome.ALLOWED), (False, AuditOutcome.DENIED)],
)
def test_audit_records_both_outcomes(allowed: bool, outcome: AuditOutcome) -> None:
    """``audit`` is the primitive behind both branches; neither may be dropped."""
    record = audit("bob", "approve", CHANGE_RESOURCE, allowed, INJECTED_AT)

    assert record.outcome is outcome
    assert (record.actor, record.action, record.resource, record.at) == (
        "bob",
        "approve",
        CHANGE_RESOURCE,
        INJECTED_AT,
    )


def test_an_audit_record_carries_every_field_an_audit_needs() -> None:
    """Actor, action, resource, outcome and time are all present and populated."""
    record = audit("bob", "approve", CHANGE_RESOURCE, True, INJECTED_AT, detail="second pair")

    field_names = {field.name for field in dataclasses.fields(record)}
    assert {"actor", "action", "resource", "outcome", "at"} <= field_names
    assert (record.actor, record.action, record.resource, record.at) == (
        "bob",
        "approve",
        CHANGE_RESOURCE,
        INJECTED_AT,
    )
    assert record.outcome is AuditOutcome.ALLOWED
    assert record.detail == "second pair"


def test_the_timestamp_comes_from_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    """A patched clock returning another value must not reach the record. AGENT.md §5."""
    monkeypatch.setattr(time, "time", lambda: 0.0)
    monkeypatch.setattr(time, "monotonic", lambda: 0.0)

    record = audit("bob", "approve", CHANGE_RESOURCE, True, INJECTED_AT)

    assert record.at == INJECTED_AT


def test_the_kernel_reads_no_clock_and_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """A decision module touches neither clock nor network. AGENT.md §5."""
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

    operator = _principal("alice", Role.OPERATOR)
    submitter_and_approver = _principal("bob", Role.APPROVER)

    permissions_for(operator)
    authorize(operator, Permission.SUBMIT_CHANGE)
    may_approve(submitter_and_approver, "bob")
    may_approve(submitter_and_approver, "alice")
    audit("bob", "approve", CHANGE_RESOURCE, False, INJECTED_AT)
    authorize_and_audit(operator, Permission.SUBMIT_CHANGE, CHANGE_RESOURCE, INJECTED_AT)
    authorize_and_audit(operator, Permission.MANAGE_USERS, CHANGE_RESOURCE, INJECTED_AT)

    assert clock_reads == []
    assert sockets == []


def test_the_same_input_gives_the_same_decision_and_record() -> None:
    """Purity shows up as equality: nothing hidden varies between two calls."""
    operator = _principal("alice", Role.OPERATOR)
    viewer = _principal("carol", Role.VIEWER)

    assert permissions_for(operator) == permissions_for(operator)
    assert authorize(operator, Permission.SUBMIT_CHANGE) == authorize(
        operator, Permission.SUBMIT_CHANGE
    )
    assert authorize_and_audit(
        operator, Permission.SUBMIT_CHANGE, CHANGE_RESOURCE, INJECTED_AT
    ) == authorize_and_audit(operator, Permission.SUBMIT_CHANGE, CHANGE_RESOURCE, INJECTED_AT)
    assert authorize_and_audit(
        viewer, Permission.APPROVE_CHANGE, CHANGE_RESOURCE, INJECTED_AT
    ) == authorize_and_audit(viewer, Permission.APPROVE_CHANGE, CHANGE_RESOURCE, INJECTED_AT)
    assert audit("bob", "approve", CHANGE_RESOURCE, True, INJECTED_AT) == audit(
        "bob", "approve", CHANGE_RESOURCE, True, INJECTED_AT
    )


def test_a_record_is_frozen() -> None:
    """An audit record is evidence; it must not be editable after the fact."""
    record = audit("bob", "approve", CHANGE_RESOURCE, True, INJECTED_AT)

    with pytest.raises(dataclasses.FrozenInstanceError):
        record.outcome = AuditOutcome.DENIED
