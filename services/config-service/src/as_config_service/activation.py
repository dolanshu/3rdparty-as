"""Coordinate rule activation and its APPLIED journal transition."""

from __future__ import annotations

from typing import Any, Protocol

from as_config_service.change_order import (
    ManagedRuleChangeAction,
    mark_applied,
)
from as_config_service.change_order_store import (
    ChangeOrderNotFoundError,
    PostgresChangeOrderStore,
    StoredChangeOrder,
)
from as_config_service.managed_rule_store import PostgresManagedRuleStore


class _Connection(Protocol):
    info: Any


def _require_idle_connection(connection: _Connection) -> None:
    from psycopg.pq import TransactionStatus

    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise RuntimeError(
            "apply_distributed_change requires an idle connection with no active transaction"
        )


def apply_distributed_change(
    change_order_store: PostgresChangeOrderStore,
    managed_rule_store: PostgresManagedRuleStore,
    change_id: str,
    expected_change_order_revision: int,
    actor: str,
    now: float,
) -> StoredChangeOrder:
    """Apply a proposal and append APPLIED in one PostgreSQL transaction.

    The stores must share a dedicated, idle connection that this coordinator
    exclusively owns for the duration of the call. Do not share the connection
    concurrently with unrelated operations; this coordinator has no global lock.
    """
    connection = change_order_store.connection
    if managed_rule_store.connection is not connection:
        raise ValueError("change-order and managed-rule stores must share one connection")
    _require_idle_connection(connection)

    try:
        stored_order = change_order_store.get(change_id)
        if stored_order is None:
            raise ChangeOrderNotFoundError(f"change order {change_id!r} does not exist")
        applied_order = mark_applied(stored_order.order, actor, now)
        proposal = stored_order.order.managed_rule_change
        if proposal is not None:
            if proposal.action is ManagedRuleChangeAction.CREATE:
                assert proposal.proposed_rule is not None
                managed_rule_store.create(
                    proposal.proposed_rule,
                    change_id,
                    actor,
                    now,
                    commit=False,
                )
            else:
                assert proposal.expected_revision is not None
                managed_rule_store.append(
                    proposal.rule_id,
                    proposal.proposed_rule,
                    change_id,
                    actor,
                    now,
                    expected_revision=proposal.expected_revision,
                    commit=False,
                )
        result = change_order_store.append_transition(
            applied_order,
            expected_revision=expected_change_order_revision,
            commit=False,
        )
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
