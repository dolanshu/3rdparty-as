"""PostgreSQL E2E: managed-rule propose → approval → distribution → activation."""

from __future__ import annotations

import json
import os
import sys
import uuid
import warnings
from collections.abc import Callable, Iterator
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request

import pytest
from fastapi import Request as FastAPIRequest
from fastapi.testclient import TestClient

from as_config_service.api import ApiIdentity, create_app
from as_config_service.as_instance import AsInstance, AsUseCase
from as_config_service.as_instance_store import PostgresAsInstanceStore
from as_config_service.audit_store import PostgresAuditStore
from as_config_service.change_order import ChangeState
from as_config_service.change_order_store import PostgresChangeOrderStore
from as_config_service.distribution_store import PostgresDistributionStore
from as_config_service.distributor import DistributionState
from as_config_service.managed_rule import MatchField, MatchMode, TargetService
from as_config_service.managed_rule_store import PostgresManagedRuleStore
from as_config_service.postgres_store import PostgresVersionStore
from as_platform.api.contract import RuleDTO

pytestmark = pytest.mark.integration

TEST_DSN = os.environ.get(
    "AS_PG_TEST_DSN", "postgresql://postgres:secret@127.0.0.1:55432/as_config"
)
_CONNECT_TIMEOUT_SECONDS = 3
_NOW = 1_700_000_000.0
_AUDIT_RESOURCE_HMAC_KEY = b"test-audit-resource-key-32-bytes"
_CHANGE_ID = "co-managed-pipeline-e2e"
_RULE_ID = "rule-called-prefix-1"
_PLAN_VERSION = 1
_NETWORK_UNAVAILABLE_MESSAGES = (
    "connection refused",
    "connection timed out",
    "timeout expired",
    "operation timed out",
    "no route to host",
    "network is unreachable",
)


class _HttpOk:
    def __init__(self, body: bytes = b"") -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return 200

    def __enter__(self) -> _HttpOk:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


@dataclass(frozen=True)
class PgHarness:
    change_order_store: PostgresChangeOrderStore
    managed_rule_store: PostgresManagedRuleStore
    distribution_store: PostgresDistributionStore
    version_store: PostgresVersionStore
    as_instance_store: PostgresAsInstanceStore
    audit_store: PostgresAuditStore
    connection: Any
    prefix: str
    runtime_role: str


def _is_network_unavailable(exc: BaseException, operational_error: type[BaseException]) -> bool:
    if not isinstance(exc, operational_error):
        return False
    normalized = str(exc).lower()
    return any(marker in normalized for marker in _NETWORK_UNAVAILABLE_MESSAGES)


@pytest.fixture()
def pg() -> Iterator[PgHarness]:
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql

    parsed = urlparse(TEST_DSN)
    connection = None
    prefix = f"managed_pipeline_{uuid.uuid4().hex[:10]}"
    audit_schema = f"{prefix}_audit"
    runtime_role = f"{prefix}_runtime"
    role_created = False
    schema_created = False
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

        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(prefix)))
        schema_created = True
        cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(runtime_role)))
        role_created = True
        connection.commit()

        change_order_store = PostgresChangeOrderStore(
            connection, prefix=f"{prefix}_orders", schema=prefix
        )
        managed_rule_store = PostgresManagedRuleStore(
            connection, prefix=f"{prefix}_rules", schema=prefix
        )
        distribution_store = PostgresDistributionStore(
            connection, prefix=f"{prefix}_distribution", schema=prefix
        )
        as_instance_store = PostgresAsInstanceStore(
            connection, prefix=f"{prefix}_instances", schema=prefix
        )
        change_order_store.ensure_schema()
        managed_rule_store.ensure_schema()
        distribution_store.ensure_schema()
        as_instance_store.ensure_schema()
        version_table = f"{prefix}_config_versions"
        version_store = PostgresVersionStore(connection, table=version_table)
        version_store.ensure_schema()
        audit_store = PostgresAuditStore(connection, prefix=f"{prefix}_audit", schema=audit_schema)
        audit_store.ensure_schema(runtime_role=runtime_role)

        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(prefix), sql.Identifier(runtime_role)
            )
        )
        for table in (
            change_order_store.heads_table,
            change_order_store.events_table,
            managed_rule_store.heads_table,
            managed_rule_store.events_table,
            distribution_store.heads_table,
            distribution_store.events_table,
        ):
            cursor.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE ON TABLE {} TO {}").format(
                    sql.SQL(table), sql.Identifier(runtime_role)
                )
            )
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {} TO {}").format(
                sql.SQL(as_instance_store.table), sql.Identifier(runtime_role)
            )
        )
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT ON TABLE {} TO {}").format(
                sql.Identifier(version_table), sql.Identifier(runtime_role)
            )
        )
        connection.commit()
        cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(runtime_role)))
        cursor.execute("SELECT current_user")
        assert cursor.fetchone()[0] == runtime_role
        connection.commit()

        change_order_store = PostgresChangeOrderStore(
            connection, prefix=f"{prefix}_orders", schema=prefix
        )
        managed_rule_store = PostgresManagedRuleStore(
            connection, prefix=f"{prefix}_rules", schema=prefix
        )
        distribution_store = PostgresDistributionStore(
            connection, prefix=f"{prefix}_distribution", schema=prefix
        )
        as_instance_store = PostgresAsInstanceStore(
            connection, prefix=f"{prefix}_instances", schema=prefix
        )
        audit_store = PostgresAuditStore(connection, prefix=f"{prefix}_audit", schema=audit_schema)
        version_store = PostgresVersionStore(connection, table=version_table)
        yield PgHarness(
            change_order_store,
            managed_rule_store,
            distribution_store,
            version_store,
            as_instance_store,
            audit_store,
            connection,
            prefix,
            runtime_role,
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
                attempt_cleanup(connection.rollback)
                try:
                    cursor.execute("RESET ROLE")
                    connection.commit()
                except BaseException as exc:
                    cleanup_errors.append(exc)
                    attempt_cleanup(connection.rollback)
                attempt_cleanup_statement(f'DROP SCHEMA IF EXISTS "{audit_schema}" CASCADE', cursor)
                if schema_created:
                    attempt_cleanup_statement(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(prefix)),
                        cursor,
                    )
                    attempt_cleanup_statement(
                        sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                            sql.Identifier(f"{prefix}_config_versions")
                        ),
                        cursor,
                    )
                if role_created:
                    attempt_cleanup_statement(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(runtime_role)),
                        cursor,
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


def _called_rule_payload() -> dict[str, object]:
    return {
        "rule_id": _RULE_ID,
        "name": "International called prefix",
        "match_field": MatchField.CALLED.value,
        "match_mode": MatchMode.PREFIX.value,
        "match_value": "+86138",
        "target_service": TargetService.TRANSLATION.value,
        "enabled": True,
        "target_detail": "return-uas",
    }


def _api_client(
    pg: PgHarness,
    *,
    user_id: str,
    now: float,
    notify_opener: Callable[..., Any] | None = None,
) -> TestClient:
    identity = type("Identity", (), {"user_id": user_id})()

    def resolve_identity(request: FastAPIRequest) -> ApiIdentity:
        return identity

    return TestClient(
        create_app(
            managed_rule_store=pg.managed_rule_store,
            change_order_store=pg.change_order_store,
            resolve_identity=resolve_identity,
            can_read_config=lambda candidate: True,
            can_submit_change=lambda candidate: True,
            can_approve_change=lambda candidate: True,
            now=lambda: now,
            new_change_id=lambda: _CHANGE_ID,
            distribution_store=pg.distribution_store,
            version_store=pg.version_store,
            as_instance_store=pg.as_instance_store,
            audit_store=pg.audit_store,
            audit_resource_hmac_key=_AUDIT_RESOURCE_HMAC_KEY,
            fleet_notify_opener=notify_opener,
        )
    )


def test_managed_rule_proposal_submit_approve_distribute_and_activate_compiled_bundle(
    pg: PgHarness,
) -> None:
    notify_calls: list[Request] = []

    def notify_opener(request: Request, *, timeout: float) -> _HttpOk:
        notify_calls.append(request)
        return _HttpOk()

    for instance_id in ("as-1", "as-2"):
        pg.as_instance_store.create(
            AsInstance(
                instance_id=instance_id,
                use_case=AsUseCase.TRANSLATION,
                notify_url="http://notify.test/hook",
                health_url=None,
                enabled=True,
            ),
            "inv-seed",
            "ops-alice",
            _NOW,
        )
    pg.connection.commit()

    alice = _api_client(pg, user_id="ops-alice", now=_NOW + 1.0, notify_opener=notify_opener)
    bob = _api_client(pg, user_id="mgr-bob", now=_NOW + 10.0, notify_opener=notify_opener)

    proposed = alice.post("/internal/v1/managed-rules", json=_called_rule_payload())
    assert proposed.status_code == 201, proposed.text
    draft = proposed.json()
    assert draft["record"]["order"]["state"] == ChangeState.DRAFT.value
    assert draft["record"]["order"]["bundle"]["rules"] == []
    proposal = draft["record"]["order"]["managed_rule_change"]
    assert proposal is not None
    assert proposal["action"] == "create"
    assert proposal["proposed_rule"]["match_field"] == "called"
    assert proposal["proposed_rule"]["match_mode"] == "prefix"
    assert pg.managed_rule_store.get(_RULE_ID) is None
    pg.connection.commit()

    submitted = alice.post(f"/internal/v1/change-orders/{_CHANGE_ID}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["record"]["order"]["state"] == ChangeState.SUBMITTED.value
    pg.connection.commit()

    approved = bob.post(f"/internal/v1/change-orders/{_CHANGE_ID}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["record"]["order"]["state"] == ChangeState.APPROVED.value
    approved_revision = approved.json()["revision"]
    pg.connection.commit()

    distribution_path = f"/internal/v1/change-orders/{_CHANGE_ID}/distribution"
    started = bob.post(
        distribution_path,
        json={
            "version": _PLAN_VERSION,
            "batches": [["as-1"], ["as-2"]],
            "expected_change_order_revision": approved_revision,
        },
    )
    assert started.status_code == 201, started.text
    assert started.json()["distribution"]["state"] == DistributionState.IN_PROGRESS.value
    assert started.json()["change_order"]["record"]["order"]["state"] == (
        ChangeState.DISTRIBUTING.value
    )
    assert len(notify_calls) == 1
    assert json.loads(notify_calls[0].data.decode("utf-8")) == {
        "change_id": _CHANGE_ID,
        "version": _PLAN_VERSION,
        "bundle_version": str(_PLAN_VERSION),
    }
    distributing_revision = started.json()["change_order"]["revision"]
    pg.connection.commit()

    partial = bob.post(
        f"{distribution_path}/reports",
        json={"expected_distribution_revision": 1, "reports": {"as-1": True}},
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["distribution"]["state"] == DistributionState.IN_PROGRESS.value
    assert partial.json()["change_order"] is None
    assert pg.managed_rule_store.get(_RULE_ID) is None
    pg.connection.commit()

    completed = bob.post(
        f"{distribution_path}/reports",
        json={"expected_distribution_revision": 2, "reports": {"as-2": True}},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["distribution"]["state"] == DistributionState.COMPLETED.value
    applied = completed.json()["change_order"]
    assert applied is not None
    assert applied["record"]["order"]["state"] == ChangeState.APPLIED.value
    assert applied["revision"] == distributing_revision + 1
    pg.connection.commit()

    active = pg.managed_rule_store.get(_RULE_ID)
    assert active is not None
    assert active.rule.match_field is MatchField.CALLED
    assert active.rule.match_mode is MatchMode.PREFIX
    assert active.rule.match_value == "+86138"
    assert active.change_id == _CHANGE_ID

    stored_version = pg.version_store.latest()
    assert stored_version is not None
    assert stored_version.change_id == _CHANGE_ID
    assert stored_version.bundle.version == str(_PLAN_VERSION)
    assert stored_version.bundle.rules == (RuleDTO(_RULE_ID, "+86138", "translate", "return-uas"),)
    assert pg.version_store.history()[-1].bundle == stored_version.bundle

    history = pg.distribution_store.history(_CHANGE_ID)
    assert [(item.revision, item.action) for item in history] == [
        (1, "begin"),
        (2, "batch_result"),
        (3, "batch_result"),
    ]
    order_history = pg.change_order_store.history(_CHANGE_ID)
    assert [item.order.state for item in order_history] == [
        ChangeState.DRAFT,
        ChangeState.SUBMITTED,
        ChangeState.APPROVED,
        ChangeState.DISTRIBUTING,
        ChangeState.APPLIED,
    ]
