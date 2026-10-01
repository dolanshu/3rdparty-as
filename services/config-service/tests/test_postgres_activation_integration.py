"""PostgreSQL integration coverage for atomic rule activation and APPLIED."""

from __future__ import annotations

import os
import sys
import threading
import uuid
import warnings
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

import as_config_service.api as api_module
from as_config_service.activation import apply_distributed_change
from as_config_service.api import ApiIdentity, create_app
from as_config_service.change_order import (
    ChangeOrder,
    ChangeState,
    ManagedRuleChange,
    ManagedRuleChangeAction,
    approve,
    begin_distribution,
    submit,
)
from as_config_service.change_order_store import (
    PostgresChangeOrderStore,
    StaleChangeOrderRevisionError,
)
from as_config_service.distribution_store import PostgresDistributionStore
from as_config_service.distributor import DistributionState
from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService
from as_config_service.managed_rule_store import PostgresManagedRuleStore
from as_platform.api.contract import ConfigBundle, RuleDTO, ToggleDTO

pytestmark = pytest.mark.integration

TEST_DSN = os.environ.get(
    "AS_PG_TEST_DSN", "postgresql://postgres:secret@127.0.0.1:55432/as_config"
)
_CONNECT_TIMEOUT_SECONDS = 3
_NOW = 1_700_000_000.0
_NETWORK_UNAVAILABLE_MESSAGES = (
    "connection refused",
    "connection timed out",
    "timeout expired",
    "operation timed out",
    "no route to host",
    "network is unreachable",
)


@dataclass(frozen=True)
class PgHarness:
    change_order_store: PostgresChangeOrderStore
    managed_rule_store: PostgresManagedRuleStore
    distribution_store: PostgresDistributionStore
    connection: Any
    prefix: str


def _is_network_unavailable(exc: BaseException, operational_error: type[BaseException]) -> bool:
    if not isinstance(exc, operational_error):
        return False
    normalized = str(exc).lower()
    return any(marker in normalized for marker in _NETWORK_UNAVAILABLE_MESSAGES)


@pytest.fixture()
def pg() -> Iterator[PgHarness]:
    psycopg = pytest.importorskip("psycopg")
    parsed = urlparse(TEST_DSN)
    connection = None
    change_order_store = None
    managed_rule_store = None
    distribution_store = None
    prefix = f"activation_test_{uuid.uuid4().hex[:10]}"
    try:
        try:
            connection = psycopg.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
        except Exception as exc:
            if _is_network_unavailable(exc, psycopg.OperationalError):
                pytest.skip(
                    f"no PostgreSQL server reachable at {parsed.hostname}:{parsed.port}: {exc}"
                )
            raise

        cursor = connection.cursor()
        cursor.execute("SHOW server_version_num")
        server_version_num = int(cursor.fetchone()[0])
        assert server_version_num >= 120000, (
            f"PostgreSQL server_version_num={server_version_num}; "
            "PostgreSQL 12 or newer is required"
        )

        change_order_store = PostgresChangeOrderStore(connection, prefix=f"{prefix}_orders")
        managed_rule_store = PostgresManagedRuleStore(connection, prefix=f"{prefix}_rules")
        distribution_store = PostgresDistributionStore(connection, prefix=f"{prefix}_distribution")
        change_order_store.ensure_schema()
        managed_rule_store.ensure_schema()
        distribution_store.ensure_schema()
        yield PgHarness(
            change_order_store, managed_rule_store, distribution_store, connection, prefix
        )
    finally:
        primary_exception = sys.exc_info()[1]
        cleanup_errors: list[BaseException] = []

        def attempt_cleanup(action: Any) -> None:
            try:
                action()
            except BaseException as exc:
                cleanup_errors.append(exc)

        def attempt_cleanup_statement(statement: str, cursor: Any) -> None:
            attempt_cleanup(connection.rollback)
            try:
                cursor.execute(statement)
                connection.commit()
            except BaseException as exc:
                cleanup_errors.append(exc)
                attempt_cleanup(connection.rollback)

        if connection is not None:
            cursor = None
            try:
                cursor = connection.cursor()
            except BaseException as exc:
                cleanup_errors.append(exc)
            if cursor is not None:
                for store in (change_order_store, managed_rule_store, distribution_store):
                    if store is None:
                        continue
                    attempt_cleanup_statement(
                        f"DROP TABLE IF EXISTS {store.events_table} CASCADE", cursor
                    )
                    attempt_cleanup_statement(
                        f"DROP TABLE IF EXISTS {store.heads_table} CASCADE", cursor
                    )
                    attempt_cleanup_statement(
                        f"DROP FUNCTION IF EXISTS {store.guard_function}()", cursor
                    )
                attempt_cleanup(getattr(cursor, "close", lambda: None))
            attempt_cleanup(connection.close)

        if cleanup_errors:
            details = "; ".join(f"{type(exc).__name__}: {exc}" for exc in cleanup_errors)
            message = f"PostgreSQL fixture cleanup failed: {details}"
            if primary_exception is not None:
                with suppress(BaseException):
                    warnings.warn(message, RuntimeWarning, stacklevel=2)
            else:
                raise RuntimeError(message) from cleanup_errors[0]


def _rule(rule_id: str = "rule-1", **overrides: object) -> ManagedRule:
    values: dict[str, object] = {
        "rule_id": rule_id,
        "name": "International callers",
        "match_field": MatchField.CALLING,
        "match_mode": MatchMode.PREFIX,
        "match_value": "+8613",
        "target_service": TargetService.TRANSLATION,
        "enabled": True,
        "target_detail": None,
    }
    values.update(overrides)
    return ManagedRule(**values)  # type: ignore[arg-type]


def _distributing_order(
    pg: PgHarness, proposal: ManagedRuleChange | None, change_id: str = "co-activation"
) -> tuple[ChangeOrder, int]:
    order = ChangeOrder(
        change_id=change_id,
        state=ChangeState.DRAFT,
        bundle=ConfigBundle(
            version="v1",
            rules=(RuleDTO("runtime-rule", "+8613", "translate", "return-uas"),),
            toggles=(ToggleDTO("translation.v2", False, "remove after M6"),),
        ),
        created_by="ops-alice",
        created_at=_NOW,
        managed_rule_change=proposal,
    )
    stored = pg.change_order_store.create(order)
    submitted = submit(order, "ops-alice", _NOW + 1.0)
    stored = pg.change_order_store.append_transition(submitted, stored.revision)
    approved_order = approve(submitted, "mgr-bob", _NOW + 2.0)
    stored = pg.change_order_store.append_transition(approved_order, stored.revision)
    distributing = begin_distribution(approved_order, "ops-alice", _NOW + 3.0)
    stored = pg.change_order_store.append_transition(distributing, stored.revision)
    return distributing, stored.revision


def _approved_order(
    pg: PgHarness, proposal: ManagedRuleChange | None, change_id: str
) -> tuple[ChangeOrder, int]:
    order = ChangeOrder(
        change_id=change_id,
        state=ChangeState.DRAFT,
        bundle=ConfigBundle(version="v1", rules=(), toggles=()),
        created_by="ops-alice",
        created_at=_NOW,
        managed_rule_change=proposal,
    )
    stored = pg.change_order_store.create(order)
    submitted = submit(order, "ops-alice", _NOW + 1.0)
    stored = pg.change_order_store.append_transition(submitted, stored.revision)
    approved_order = approve(submitted, "mgr-bob", _NOW + 2.0)
    stored = pg.change_order_store.append_transition(approved_order, stored.revision)
    return approved_order, stored.revision


def _api_client(pg: PgHarness, *, now: float = _NOW + 10.0) -> TestClient:
    identity = type("Identity", (), {"user_id": "ops-bob"})()

    def resolve_identity(request: Request) -> ApiIdentity:
        return identity

    return TestClient(
        create_app(
            managed_rule_store=pg.managed_rule_store,
            change_order_store=pg.change_order_store,
            resolve_identity=resolve_identity,
            can_read_config=lambda candidate: True,
            can_approve_change=lambda candidate: True,
            now=lambda: now,
            distribution_store=pg.distribution_store,
        )
    )


def _proposal_for_action(
    pg: PgHarness, action: ManagedRuleChangeAction
) -> tuple[ManagedRuleChange, ManagedRule | None]:
    original = _rule()
    if action is ManagedRuleChangeAction.CREATE:
        return ManagedRuleChange(action, original.rule_id, original, None), None
    initial = pg.managed_rule_store.create(original, "initial", "ops-alice", _NOW)
    proposed = (
        replace(original, name="Updated callers")
        if action is ManagedRuleChangeAction.UPDATE
        else None
    )
    return ManagedRuleChange(action, original.rule_id, proposed, initial.revision), original


@pytest.mark.parametrize(
    "action",
    [
        ManagedRuleChangeAction.CREATE,
        ManagedRuleChangeAction.UPDATE,
        ManagedRuleChangeAction.DELETE,
    ],
)
def test_api_distribution_reports_activate_typed_rule_proposals_and_are_idempotent(
    pg: PgHarness, action: ManagedRuleChangeAction
) -> None:
    proposal, original = _proposal_for_action(pg, action)
    approved_order, order_revision = _approved_order(pg, proposal, f"co-api-{action.value}")
    client = _api_client(pg)
    path = f"/internal/v1/change-orders/{approved_order.change_id}/distribution"

    started = client.post(
        path,
        json={
            "version": 12,
            "batches": [["as-1"], ["as-2"]],
            "expected_change_order_revision": order_revision,
        },
    )
    observed = client.get(path)
    partial = client.post(
        f"{path}/reports",
        json={"expected_distribution_revision": 1, "reports": {"as-1": True}},
    )

    assert started.status_code == 201, started.text
    assert started.json()["distribution"]["revision"] == 1
    assert started.json()["distribution"]["state"] == "in_progress"
    assert started.json()["change_order"]["record"]["order"]["state"] == "distributing"
    assert observed.status_code == 200
    assert observed.json()["revision"] == 1
    assert observed.json()["plan"]["version"] == 12
    assert partial.status_code == 200, partial.text
    assert partial.json()["distribution"]["revision"] == 2
    assert partial.json()["distribution"]["state"] == "in_progress"
    assert partial.json()["change_order"] is None
    active = pg.managed_rule_store.get("rule-1")
    if original is None:
        assert active is None
    else:
        assert active.rule == original
    pg.connection.commit()

    completed = client.post(
        f"{path}/reports",
        json={"expected_distribution_revision": 2, "reports": {"as-2": True}},
    )

    assert completed.status_code == 200, completed.text
    assert completed.json()["distribution"]["revision"] == 3
    assert completed.json()["distribution"]["state"] == "completed"
    assert completed.json()["distribution"]["completed_batches"] == 2
    assert completed.json()["distribution"]["reports"] == [
        {"instance_id": "as-1", "healthy": True},
        {"instance_id": "as-2", "healthy": True},
    ]
    applied = completed.json()["change_order"]
    assert applied["revision"] == order_revision + 2
    assert applied["record"]["order"]["state"] == "applied"
    history = pg.distribution_store.history(approved_order.change_id)
    assert [(item.revision, item.action) for item in history] == [
        (1, "begin"),
        (2, "batch_result"),
        (3, "batch_result"),
    ]
    assert [item.actor for item in history] == ["ops-bob"] * 3
    assert [item.distribution.state for item in history] == [
        DistributionState.IN_PROGRESS,
        DistributionState.IN_PROGRESS,
        DistributionState.COMPLETED,
    ]
    if action in (ManagedRuleChangeAction.CREATE, ManagedRuleChangeAction.UPDATE):
        assert pg.managed_rule_store.history("rule-1")[-1].rule == proposal.proposed_rule
    else:
        assert pg.managed_rule_store.history("rule-1")[-1].rule is None
    pg.connection.commit()

    applied_order_history_length = len(pg.change_order_store.history(approved_order.change_id))
    applied_rule_history_length = len(pg.managed_rule_store.history("rule-1"))
    pg.connection.commit()

    retry = client.post(
        f"{path}/apply", json={"expected_change_order_revision": order_revision + 1}
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["change_order"]["revision"] == applied["revision"]
    stale_retry = client.post(
        f"{path}/apply", json={"expected_change_order_revision": order_revision}
    )
    assert stale_retry.status_code == 409
    assert pg.connection.info.transaction_status.name == "IDLE"
    assert len(pg.change_order_store.history(approved_order.change_id)) == (
        applied_order_history_length
    )
    assert len(pg.managed_rule_store.history("rule-1")) == applied_rule_history_length
    pg.connection.commit()
    rollback_after_apply = client.post(
        f"{path}/rollback",
        json={
            "expected_distribution_revision": 3,
            "expected_change_order_revision": applied["revision"],
            "reason": "too late",
        },
    )
    assert rollback_after_apply.status_code == 409
    assert len(pg.managed_rule_store.history("rule-1")) == (
        1 if action is ManagedRuleChangeAction.CREATE else 2
    )
    assert len(pg.change_order_store.history(approved_order.change_id)) == applied["revision"]


def test_distribution_status_missing_returns_404_and_releases_connection(pg: PgHarness) -> None:
    response = _api_client(pg).get("/internal/v1/change-orders/no-distribution/distribution")

    assert response.status_code == 404
    assert pg.connection.info.transaction_status.name == "IDLE"


def test_api_read_releases_connection_before_distribution_start(pg: PgHarness) -> None:
    approved_order, order_revision = _approved_order(pg, None, "co-read-before-start")
    client = _api_client(pg)
    order_path = f"/internal/v1/change-orders/{approved_order.change_id}"

    missing = client.get("/internal/v1/change-orders/missing")
    assert missing.status_code == 404
    assert pg.connection.info.transaction_status.name == "IDLE"
    observed = client.get(order_path)

    assert observed.status_code == 200
    assert pg.connection.info.transaction_status.name == "IDLE"
    started = client.post(
        f"{order_path}/distribution",
        json={
            "version": 8,
            "batches": [["as-1"]],
            "expected_change_order_revision": order_revision,
        },
    )

    assert started.status_code == 201, started.text
    assert pg.connection.info.transaction_status.name == "IDLE"


def test_api_request_scope_does_not_rollback_a_preexisting_transaction(pg: PgHarness) -> None:
    pg.connection.execute("SELECT 1")
    response = _api_client(pg).get("/internal/v1/change-orders")

    assert response.status_code == 409
    assert pg.connection.info.transaction_status.name != "IDLE"
    pg.connection.rollback()
    assert pg.connection.info.transaction_status.name == "IDLE"


def test_api_serializes_distribution_mutations_on_shared_connection(
    pg: PgHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_order, first_revision = _approved_order(pg, None, "co-concurrent-first")
    second_order, second_revision = _approved_order(pg, None, "co-concurrent-second")
    first_path = f"/internal/v1/change-orders/{first_order.change_id}/distribution"
    second_path = f"/internal/v1/change-orders/{second_order.change_id}/distribution"
    first_staged = threading.Event()
    release_first = threading.Event()
    second_create_entered = threading.Event()
    second_lock_attempted = threading.Event()
    original_create = pg.distribution_store.create
    create_calls = 0
    lock_acquisitions = 0

    class ObservedLock:
        def __init__(self) -> None:
            self._lock = threading.Lock()

        def acquire(self) -> None:
            nonlocal lock_acquisitions
            lock_acquisitions += 1
            if lock_acquisitions == 2:
                second_lock_attempted.set()
            self._lock.acquire()

        def release(self) -> None:
            self._lock.release()

    monkeypatch.setattr(api_module, "Lock", lambda: ObservedLock())
    client = _api_client(pg)

    def block_after_first_stage(*args: Any, **kwargs: Any) -> Any:
        nonlocal create_calls
        create_calls += 1
        result = original_create(*args, **kwargs)
        if create_calls == 1:
            first_staged.set()
            if not release_first.wait(timeout=5):
                raise TimeoutError("first distribution request was not released")
        else:
            second_create_entered.set()
        return result

    pg.distribution_store.create = block_after_first_stage  # type: ignore[method-assign]
    first_payload = {
        "version": 1,
        "batches": [["as-1"]],
        "expected_change_order_revision": first_revision,
    }
    second_payload = {
        "version": 1,
        "batches": [["as-2"]],
        "expected_change_order_revision": second_revision,
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(client.post, first_path, json=first_payload)
        try:
            assert first_staged.wait(timeout=5)
            second_future = executor.submit(client.post, second_path, json=second_payload)
            assert second_lock_attempted.wait(timeout=5)
            assert not second_create_entered.is_set()
        finally:
            release_first.set()
        first_response = first_future.result(timeout=5)
        second_response = second_future.result(timeout=5)

    assert first_response.status_code == second_response.status_code == 201
    assert pg.connection.info.transaction_status.name == "IDLE"
    for order in (first_order, second_order):
        distribution_history = pg.distribution_store.history(order.change_id)
        order_history = pg.change_order_store.history(order.change_id)
        assert [(item.revision, item.action) for item in distribution_history] == [(1, "begin")]
        assert [item.revision for item in order_history] == [1, 2, 3, 4]
        assert order_history[-1].order.state is ChangeState.DISTRIBUTING
    pg.connection.commit()


def test_direct_apply_before_distribution_completion_cannot_activate(pg: PgHarness) -> None:
    proposed = _rule()
    approved_order, order_revision = _approved_order(
        pg,
        ManagedRuleChange(ManagedRuleChangeAction.CREATE, proposed.rule_id, proposed, None),
        "co-apply-before-complete",
    )
    client = _api_client(pg)
    path = f"/internal/v1/change-orders/{approved_order.change_id}/distribution"
    started = client.post(
        path,
        json={
            "version": 2,
            "batches": [["as-1"]],
            "expected_change_order_revision": order_revision,
        },
    )
    rejected = client.post(
        f"{path}/apply", json={"expected_change_order_revision": order_revision + 1}
    )

    assert started.status_code == 201
    assert rejected.status_code == 409
    assert pg.managed_rule_store.get(proposed.rule_id) is None
    pg.connection.commit()
    current = pg.change_order_store.get(approved_order.change_id)
    assert current.revision == order_revision + 1
    assert current.order.state is ChangeState.DISTRIBUTING


def test_unhealthy_report_rolls_back_distribution_and_order_atomically(pg: PgHarness) -> None:
    proposed = _rule()
    approved_order, order_revision = _approved_order(
        pg,
        ManagedRuleChange(ManagedRuleChangeAction.CREATE, proposed.rule_id, proposed, None),
        "co-unhealthy-report",
    )
    client = _api_client(pg)
    path = f"/internal/v1/change-orders/{approved_order.change_id}/distribution"
    client.post(
        path,
        json={
            "version": 2,
            "batches": [["as-1"]],
            "expected_change_order_revision": order_revision,
        },
    )

    rolled_back = client.post(
        f"{path}/reports",
        json={"expected_distribution_revision": 1, "reports": {"as-1": False}},
    )

    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["distribution"]["state"] == "rolled_back"
    assert rolled_back.json()["distribution"]["rollback_reason"] == "health check failed"
    assert rolled_back.json()["change_order"]["record"]["order"]["state"] == "rolled_back"
    assert pg.distribution_store.history(approved_order.change_id)[-1].revision == 2
    assert pg.change_order_store.get(approved_order.change_id).revision == order_revision + 2
    assert pg.managed_rule_store.get(proposed.rule_id) is None


def test_manual_rollback_is_atomic_and_stale_report_is_rejected(pg: PgHarness) -> None:
    approved_order, order_revision = _approved_order(pg, None, "co-manual-rollback")
    client = _api_client(pg)
    path = f"/internal/v1/change-orders/{approved_order.change_id}/distribution"
    client.post(
        path,
        json={
            "version": 2,
            "batches": [["as-1"]],
            "expected_change_order_revision": order_revision,
        },
    )
    stale = client.post(
        f"{path}/reports",
        json={"expected_distribution_revision": 2, "reports": {"as-1": True}},
    )
    rolled_back = client.post(
        f"{path}/rollback",
        json={
            "expected_distribution_revision": 1,
            "expected_change_order_revision": order_revision + 1,
            "reason": "operator requested rollback",
        },
    )

    assert stale.status_code == 409
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["distribution"]["state"] == "rolled_back"
    assert rolled_back.json()["distribution"]["rollback_reason"] == "operator requested rollback"
    assert rolled_back.json()["change_order"]["record"]["order"]["state"] == "rolled_back"
    assert pg.managed_rule_store.list_latest() == ()
    assert len(pg.distribution_store.history(approved_order.change_id)) == 2


def test_completed_distribution_survives_activation_failure_and_can_be_retried(
    pg: PgHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposed = _rule()
    approved_order, order_revision = _approved_order(
        pg,
        ManagedRuleChange(ManagedRuleChangeAction.CREATE, proposed.rule_id, proposed, None),
        "co-activation-retry",
    )
    client = _api_client(pg)
    path = f"/internal/v1/change-orders/{approved_order.change_id}/distribution"
    client.post(
        path,
        json={
            "version": 2,
            "batches": [["as-1"]],
            "expected_change_order_revision": order_revision,
        },
    )
    coordinator = api_module.apply_distributed_change

    def fail_activation(*args: object, **kwargs: object) -> Any:
        raise RuntimeError("temporary activation failure")

    monkeypatch.setattr(api_module, "apply_distributed_change", fail_activation)
    failed = client.post(
        f"{path}/reports",
        json={"expected_distribution_revision": 1, "reports": {"as-1": True}},
    )

    assert failed.status_code == 500
    assert pg.connection.info.transaction_status.name == "IDLE"
    assert (
        pg.distribution_store.get(approved_order.change_id).distribution.state
        is DistributionState.COMPLETED
    )
    assert (
        pg.change_order_store.get(approved_order.change_id).order.state is ChangeState.DISTRIBUTING
    )
    assert pg.managed_rule_store.get(proposed.rule_id) is None
    pg.connection.commit()

    monkeypatch.setattr(api_module, "apply_distributed_change", coordinator)
    retried = client.post(
        f"{path}/apply", json={"expected_change_order_revision": order_revision + 1}
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["change_order"]["record"]["order"]["state"] == "applied"
    assert pg.managed_rule_store.get(proposed.rule_id).rule == proposed


def test_create_proposal_and_applied_transition_share_one_transaction(pg: PgHarness) -> None:
    proposed = _rule()
    distributing, revision = _distributing_order(
        pg,
        ManagedRuleChange(ManagedRuleChangeAction.CREATE, proposed.rule_id, proposed, None),
    )

    applied = apply_distributed_change(
        pg.change_order_store,
        pg.managed_rule_store,
        distributing.change_id,
        revision,
        "ops-alice",
        _NOW + 4.0,
    )

    rule_history = pg.managed_rule_store.history(proposed.rule_id)
    order_history = pg.change_order_store.history(distributing.change_id)
    assert [(item.revision, item.rule) for item in rule_history] == [(1, proposed)]
    assert rule_history[0].change_id == distributing.change_id
    assert rule_history[0].actor == "ops-alice"
    assert rule_history[0].created_at == _NOW + 4.0
    assert [(item.revision, item.order.state) for item in order_history] == [
        (1, ChangeState.DRAFT),
        (2, ChangeState.SUBMITTED),
        (3, ChangeState.APPROVED),
        (4, ChangeState.DISTRIBUTING),
        (5, ChangeState.APPLIED),
    ]
    assert applied == order_history[-1]
    assert applied.order.audit[-1].action == "mark_applied"
    assert applied.order.audit[-1].actor == "ops-alice"
    assert applied.order.audit[-1].at == _NOW + 4.0
    cursor = pg.connection.cursor()
    cursor.execute(
        f"SELECT COUNT(*) FROM {pg.managed_rule_store.events_table} WHERE rule_id = %s",
        (proposed.rule_id,),
    )
    assert cursor.fetchone()[0] == 1
    cursor.execute(
        f"SELECT COUNT(*) FROM {pg.change_order_store.events_table} "
        "WHERE change_id = %s AND audit_entry_json IS NOT NULL",
        (distributing.change_id,),
    )
    assert cursor.fetchone()[0] == 4


@pytest.mark.parametrize("action", [ManagedRuleChangeAction.UPDATE, ManagedRuleChangeAction.DELETE])
def test_update_and_delete_become_active_only_when_marked_applied(
    pg: PgHarness, action: ManagedRuleChangeAction
) -> None:
    original = _rule()
    initial = pg.managed_rule_store.create(original, "initial", "ops-alice", _NOW)
    proposed = (
        replace(original, name="Updated callers")
        if action is ManagedRuleChangeAction.UPDATE
        else None
    )
    proposal = ManagedRuleChange(action, original.rule_id, proposed, initial.revision)
    distributing, revision = _distributing_order(pg, proposal, f"co-{action.value}")
    assert pg.managed_rule_store.get(original.rule_id) == initial
    assert pg.change_order_store.get(distributing.change_id).order.state is ChangeState.DISTRIBUTING
    pg.connection.commit()

    applied = apply_distributed_change(
        pg.change_order_store,
        pg.managed_rule_store,
        distributing.change_id,
        revision,
        "ops-alice",
        _NOW + 4.0,
    )

    history = pg.managed_rule_store.history(original.rule_id)
    assert [item.revision for item in history] == [1, 2]
    assert history[-1].rule == proposed
    assert pg.managed_rule_store.get(original.rule_id) == history[-1]
    assert applied.order.state is ChangeState.APPLIED
    assert applied.revision == revision + 1


def test_stale_order_revision_rolls_back_provisional_managed_rule_write(pg: PgHarness) -> None:
    proposed = _rule()
    distributing, revision = _distributing_order(
        pg,
        ManagedRuleChange(ManagedRuleChangeAction.CREATE, proposed.rule_id, proposed, None),
    )

    with pytest.raises(StaleChangeOrderRevisionError):
        apply_distributed_change(
            pg.change_order_store,
            pg.managed_rule_store,
            distributing.change_id,
            revision - 1,
            "ops-alice",
            _NOW + 4.0,
        )

    assert pg.managed_rule_store.get(proposed.rule_id) is None
    assert pg.managed_rule_store.history(proposed.rule_id) == ()
    assert pg.change_order_store.get(distributing.change_id).revision == revision
    assert pg.change_order_store.get(distributing.change_id).order.state is ChangeState.DISTRIBUTING
    cursor = pg.connection.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {pg.managed_rule_store.events_table}")
    assert cursor.fetchone()[0] == 0


def test_active_caller_transaction_is_rejected_without_store_changes(pg: PgHarness) -> None:
    psycopg = pytest.importorskip("psycopg")
    proposed = _rule()
    distributing, revision = _distributing_order(
        pg,
        ManagedRuleChange(ManagedRuleChangeAction.CREATE, proposed.rule_id, proposed, None),
        "co-active-caller-transaction",
    )
    order_history = pg.change_order_store.history(distributing.change_id)
    rule_history = pg.managed_rule_store.history(proposed.rule_id)
    pg.connection.commit()

    cursor = pg.connection.cursor()
    cursor.execute("SELECT 1")
    assert pg.connection.info.transaction_status is psycopg.pq.TransactionStatus.INTRANS
    try:
        with pytest.raises(RuntimeError, match="requires an idle connection"):
            apply_distributed_change(
                pg.change_order_store,
                pg.managed_rule_store,
                distributing.change_id,
                revision,
                "ops-alice",
                _NOW + 4.0,
            )

        assert pg.connection.info.transaction_status is psycopg.pq.TransactionStatus.INTRANS
        assert pg.change_order_store.history(distributing.change_id) == order_history
        assert pg.managed_rule_store.history(proposed.rule_id) == rule_history
    finally:
        pg.connection.rollback()


def test_legacy_order_without_proposal_can_be_marked_applied(pg: PgHarness) -> None:
    distributing, revision = _distributing_order(pg, None, "co-legacy")

    applied = apply_distributed_change(
        pg.change_order_store,
        pg.managed_rule_store,
        distributing.change_id,
        revision,
        "ops-alice",
        _NOW + 4.0,
    )

    assert applied.order.state is ChangeState.APPLIED
    assert pg.managed_rule_store.list_latest() == ()
    assert pg.managed_rule_store.history("rule-1") == ()


def test_different_connection_objects_are_rejected_before_state_changes(pg: PgHarness) -> None:
    psycopg = pytest.importorskip("psycopg")
    connection = psycopg.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    try:
        other_managed_store = PostgresManagedRuleStore(
            connection, prefix=pg.managed_rule_store.prefix
        )
        distributing, revision = _distributing_order(
            pg,
            ManagedRuleChange(ManagedRuleChangeAction.CREATE, "rule-1", _rule(), None),
            "co-different-connection",
        )

        with pytest.raises(ValueError, match="share one connection"):
            apply_distributed_change(
                pg.change_order_store,
                other_managed_store,
                distributing.change_id,
                revision,
                "ops-alice",
                _NOW + 4.0,
            )

        assert pg.managed_rule_store.list_latest() == ()
        assert (
            pg.change_order_store.get(distributing.change_id).order.state
            is ChangeState.DISTRIBUTING
        )
    finally:
        connection.close()
