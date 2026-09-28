"""Console authorization and audit: who may do what, and the trace it leaves.

REQ-S-4 assigns every console operation two obligations: it is authorized, and
it leaves a record. ADR-0016 puts both in the M4 control plane, and ADR-0006
makes the change order the governance loop that the audit trail has to line up
with. This module is the obligation itself, stripped of everything around it.

There is deliberately no HTTP framework, no login form, no session and no
password here. Authentication answers "who is this"; this module answers
"may they" and "what trace does either answer leave". Keeping them apart is
what lets the decision be a pure function, which is what makes it cheap to
test (AGENT.md §5).

Purity: no clock is read, no socket is opened, no global state is consulted.
When something happened is injected by the caller, so it is a fact the caller
owns rather than something this module invents.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class Role(Enum):
    """A console role. Roles are additive: a principal's powers are their union.

    Attributes:
        VIEWER: Read-only: browse rules and trace a call.
        OPERATOR: Read plus drafting a change order.
        APPROVER: Read, draft, approve and roll back a change order.
        ADMIN: Everything, including managing who holds the roles above.
    """

    VIEWER = "viewer"
    OPERATOR = "operator"
    APPROVER = "approver"
    ADMIN = "admin"


class Permission(Enum):
    """A thing a console principal may or may not do.

    Attributes:
        READ_CONFIG: Read rule versions and their history.
        SUBMIT_CHANGE: Draft a change order and hand it in for approval.
        APPROVE_CHANGE: Approve a change order written by somebody else.
        ROLLBACK_CHANGE: Roll a distributed change back.
        MANAGE_USERS: Grant and revoke roles.
    """

    READ_CONFIG = "read_config"
    SUBMIT_CHANGE = "submit_change"
    APPROVE_CHANGE = "approve_change"
    ROLLBACK_CHANGE = "rollback_change"
    MANAGE_USERS = "manage_users"


ROLE_PERMISSIONS: Mapping[Role, frozenset[Permission]] = {
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
    # ADMIN sweeping every permission is the one row that grows implicitly with
    # Permission: adding a permission grants it to ADMIN with no second edit.
    # See ADR-0016.
    Role.ADMIN: frozenset(Permission),
}


class AuditOutcome(Enum):
    """How an authorization decision ended.

    Attributes:
        ALLOWED: The principal held the permission.
        DENIED: They did not, or the two-person rule blocked them.
    """

    ALLOWED = "allowed"
    DENIED = "denied"


@dataclass(frozen=True)
class Principal:
    """Who is acting, as far as an authorization decision needs to know.

    Attributes:
        user_id: Stable identifier for the acting user. It doubles as the
            identity the two-person rule compares against whoever submitted a
            change order. See ADR-0006.
        roles: Every role the principal holds. Empty grants nothing.
    """

    user_id: str
    roles: frozenset[Role]


@dataclass(frozen=True)
class AuditRecord:
    """One line of the console audit trail. See ADR-0016.

    Attributes:
        actor: Who attempted it.
        action: What was attempted; ``authorize_and_audit`` uses the
            ``Permission`` value, so the trail reads in the same vocabulary as
            the decision.
        resource: What it was attempted on, for example ``change:co-7``.
        outcome: ALLOWED or DENIED. Both are recorded: a refusal that leaves
            no trace is invisible to the audit REQ-S-4 asks for.
        at: When it happened, injected by the caller; this module reads no
            clock (AGENT.md §5).
        detail: Optional context. It must never carry payload data, whose
            logging is off by default (AGENT.md §13).
    """

    actor: str
    action: str
    resource: str
    outcome: AuditOutcome
    at: float
    detail: str = ""


def permissions_for(principal: Principal) -> frozenset[Permission]:
    """Every permission the principal's roles grant, unioned.

    Args:
        principal: Who is acting. A role absent from ``ROLE_PERMISSIONS``
            grants nothing rather than raising: an unrecognized role must not
            become a way past the check. See ADR-0016.

    Returns:
        The union of their roles' permissions; empty when they hold no role.
    """
    granted: set[Permission] = set()
    for role in principal.roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)


def authorize(principal: Principal, permission: Permission) -> bool:
    """Whether ``principal`` may perform ``permission``.

    Fail-closed by construction: this asks whether the permission is among
    those granted, never whether it is among those withheld, so a permission
    added later is denied to everybody until a role grants it. See ADR-0016.

    Args:
        principal: Who is acting.
        permission: What they want to do.

    Returns:
        ``True`` only when one of their roles grants the permission.
    """
    return permission in permissions_for(principal)


def may_approve(approver: Principal, change_created_by: str) -> bool:
    """Whether ``approver`` may approve a change submitted by ``change_created_by``.

    The permission alone is not authority enough: whoever wrote a change is
    the person least able to judge it. See ADR-0016 and, for the approval
    record this has to line up with, ADR-0006.

    Args:
        approver: Who would approve it.
        change_created_by: Who submitted it.

    Returns:
        ``True`` when they hold APPROVE_CHANGE **and** are not the submitter.
    """
    if approver.user_id == change_created_by:
        return False
    return authorize(approver, Permission.APPROVE_CHANGE)


def audit(
    actor: str,
    action: str,
    resource: str,
    allowed: bool,
    at: float,
    detail: str = "",
) -> AuditRecord:
    """Build one audit line for a decision that has already been made.

    Both outcomes are worth recording: an allowed console operation explains a
    configuration that changed, a denied one explains an operation somebody
    tried. REQ-S-4 asks for both. See ADR-0016.

    Args:
        actor: Who attempted it.
        action: What was attempted.
        resource: What it was attempted on.
        allowed: Whether the decision allowed it.
        at: When it happened, injected by the caller.
        detail: Optional context, never payload data.

    Returns:
        The record, carrying whichever outcome ``allowed`` selected.
    """
    return AuditRecord(
        actor=actor,
        action=action,
        resource=resource,
        outcome=AuditOutcome.ALLOWED if allowed else AuditOutcome.DENIED,
        at=at,
        detail=detail,
    )


def authorize_and_audit(
    principal: Principal,
    permission: Permission,
    resource: str,
    at: float,
    detail: str = "",
) -> tuple[bool, AuditRecord]:
    """Decide and record in one call, for the resource the decision was about.

    Returning the record alongside the verdict exists because REQ-S-4 binds
    the two: a caller that can only obtain them separately will record the
    allowances and drop the refusals. See ADR-0016.

    Args:
        principal: Who is acting.
        permission: What they want to do.
        resource: What they want to do it to, recorded as ``resource``.
        at: When the attempt happened, injected by the caller.
        detail: Optional context for the record.

    Returns:
        The verdict, and the audit record of the attempt whichever way it went.
    """
    allowed = authorize(principal, permission)
    return allowed, audit(principal.user_id, permission.value, resource, allowed, at, detail)
