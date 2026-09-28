"""Operations console (layer ③, control plane).

Read-write surface for the operator: rule editing through change orders, call
trace lookup by Call-ID, live statistics. It reaches an AS only through the
AS's internal API.
"""

from __future__ import annotations

from .access import (
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

__all__: list[str] = [
    "ROLE_PERMISSIONS",
    "AuditOutcome",
    "AuditRecord",
    "Permission",
    "Principal",
    "Role",
    "audit",
    "authorize",
    "authorize_and_audit",
    "may_approve",
    "permissions_for",
]
