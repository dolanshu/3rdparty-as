"""Real-PostgreSQL coverage for authenticated config API flows. ADR-0024 draft."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import uuid
import warnings
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

import as_config_service.api as api_module
from as_config_service.api import ApiIdentity, create_app
from as_config_service.audit_store import PostgresAuditStore
from as_config_service.auth import LastEnabledConsoleAdminError, PostgresConsoleAuthStore
from as_config_service.change_order_store import PostgresChangeOrderStore
from as_config_service.managed_rule_store import PostgresManagedRuleStore
from as_console.access import AuditOutcome, Role

pytestmark = pytest.mark.integration

TEST_DSN = os.environ.get(
    "AS_PG_TEST_DSN", "postgresql://postgres:secret@127.0.0.1:55432/as_config"
)
_CONNECT_TIMEOUT_SECONDS = 3
_NOW = 1_700_000_000.0
_AUDIT_RESOURCE_HMAC_KEY = b"i" * 32
_NETWORK_UNAVAILABLE_MESSAGES = (
    "connection refused",
    "connection timed out",
    "timeout expired",
    "operation timed out",
    "no route to host",
    "network is unreachable",
)


@dataclass
class PgHarness:
    connection: Any
    driver: Any
    schema: str
    audit_schema: str
    runtime_role: str
    auth_store: PostgresConsoleAuthStore
    audit_store: PostgresAuditStore
    change_order_store: PostgresChangeOrderStore
    managed_rule_store: PostgresManagedRuleStore
    clock: list[float]


def _is_network_unavailable(exc: BaseException, operational_error: type[BaseException]) -> bool:
    if not isinstance(exc, operational_error):
        return False
    normalized = str(exc).lower()
    return any(marker in normalized for marker in _NETWORK_UNAVAILABLE_MESSAGES)


@pytest.fixture()
def pg() -> Iterator[PgHarness]:
    driver = pytest.importorskip("psycopg")
    from psycopg import sql

    parsed = urlparse(TEST_DSN)
    connection = None
    schema = f"auth_api_test_{uuid.uuid4().hex[:12]}"
    audit_schema = f"{schema}_audit"
    prefix = f"auth_api_{uuid.uuid4().hex[:10]}"
    runtime_role = f"auth_api_runtime_{uuid.uuid4().hex[:10]}"
    role_created = False
    try:
        try:
            connection = driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
        except Exception as exc:
            if _is_network_unavailable(exc, driver.OperationalError):
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
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(runtime_role)))
        role_created = True
        connection.commit()
        auth_store = PostgresConsoleAuthStore(connection, prefix=f"{prefix}_auth", schema=schema)
        change_orders = PostgresChangeOrderStore(
            connection, prefix=f"{prefix}_orders", schema=schema
        )
        managed_rules = PostgresManagedRuleStore(
            connection, prefix=f"{prefix}_rules", schema=schema
        )
        auth_store.ensure_schema()
        change_orders.ensure_schema()
        managed_rules.ensure_schema()
        audit_store = PostgresAuditStore(connection, prefix=f"{prefix}_audit", schema=audit_schema)
        audit_store.ensure_schema(runtime_role=runtime_role)

        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(schema), sql.Identifier(runtime_role)
            )
        )
        for table in (
            auth_store.users_table,
            auth_store.sessions_table,
            change_orders.heads_table,
            change_orders.events_table,
            managed_rules.heads_table,
            managed_rules.events_table,
        ):
            cursor.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE ON TABLE {} TO {}").format(
                    sql.SQL(table), sql.Identifier(runtime_role)
                )
            )
        cursor.execute(
            sql.SQL("GRANT SELECT, UPDATE ON TABLE {} TO {}").format(
                sql.SQL(auth_store.bootstrap_table), sql.Identifier(runtime_role)
            )
        )
        connection.commit()
        cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(runtime_role)))
        cursor.execute("SELECT current_user")
        assert cursor.fetchone()[0] == runtime_role
        connection.commit()

        auth_store = PostgresConsoleAuthStore(connection, prefix=f"{prefix}_auth", schema=schema)
        change_orders = PostgresChangeOrderStore(
            connection, prefix=f"{prefix}_orders", schema=schema
        )
        managed_rules = PostgresManagedRuleStore(
            connection, prefix=f"{prefix}_rules", schema=schema
        )
        audit_store = PostgresAuditStore(connection, prefix=f"{prefix}_audit", schema=audit_schema)
        yield PgHarness(
            connection,
            driver,
            schema,
            audit_schema,
            runtime_role,
            auth_store,
            audit_store,
            change_orders,
            managed_rules,
            [_NOW],
        )
    finally:
        primary_exception = sys.exc_info()[1]
        cleanup_errors: list[BaseException] = []
        if connection is not None:
            try:
                connection.rollback()
                cursor = connection.cursor()
                cursor.execute("RESET ROLE")
                connection.commit()
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
                )
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(audit_schema))
                )
                if role_created:
                    cursor.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(runtime_role))
                    )
                connection.commit()
                cursor.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
                with suppress(BaseException):
                    connection.rollback()
            try:
                connection.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            details = "; ".join(f"{type(exc).__name__}: {exc}" for exc in cleanup_errors)
            message = f"PostgreSQL fixture cleanup failed: {details}"
            if primary_exception is not None:
                with suppress(BaseException):
                    warnings.warn(message, RuntimeWarning, stacklevel=2)
            else:
                raise RuntimeError(message) from cleanup_errors[0]


def _app(pg: PgHarness, resolver: Any = None) -> Any:
    return create_app(
        managed_rule_store=pg.managed_rule_store,
        change_order_store=pg.change_order_store,
        resolve_identity=resolver,
        can_read_config=lambda _: False,
        now=lambda: pg.clock[0],
        auth_store=pg.auth_store,
        audit_store=pg.audit_store,
        audit_resource_hmac_key=_AUDIT_RESOURCE_HMAC_KEY,
    )


def _bootstrap(pg: PgHarness) -> None:
    from psycopg import sql

    cursor = pg.connection.cursor()
    cursor.execute("RESET ROLE")
    pg.connection.commit()
    try:
        pg.auth_store.bootstrap_admin("admin-1", "admin-password-long", pg.clock[0])
    finally:
        pg.connection.rollback()
        cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(pg.runtime_role)))
        cursor.execute("SELECT current_user")
        assert cursor.fetchone()[0] == pg.runtime_role
        pg.connection.commit()


def _login(client: TestClient, user_id: str, password: str) -> str:
    response = client.post(
        "/internal/v1/auth/login",
        json={"user_id": user_id, "password": password},
    )
    assert response.status_code == 200, response.text
    csrf = client.cookies.get("__Host-as_console_csrf")
    assert csrf is not None
    return csrf


def _change_order_payload() -> dict[str, object]:
    return {"bundle": {"version": "v1", "rules": [], "toggles": []}}


def test_audited_app_rejects_postgres_stores_on_different_connections(pg: PgHarness) -> None:
    other_connection = pg.driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    try:
        other_audit_store = PostgresAuditStore(
            other_connection,
            prefix=pg.audit_store.prefix,
            schema=pg.audit_store.schema,
        )
        with pytest.raises(ValueError, match="must share one connection"):
            create_app(
                managed_rule_store=pg.managed_rule_store,
                change_order_store=pg.change_order_store,
                resolve_identity=None,
                can_read_config=lambda _: False,
                auth_store=pg.auth_store,
                audit_store=other_audit_store,
                audit_resource_hmac_key=_AUDIT_RESOURCE_HMAC_KEY,
            )
    finally:
        other_connection.close()


def test_audited_app_requires_the_runtime_effective_role(pg: PgHarness) -> None:
    from psycopg import sql

    cursor = pg.connection.cursor()
    cursor.execute("RESET ROLE")
    pg.connection.commit()
    owner_audit_store = PostgresAuditStore(
        pg.connection,
        prefix=pg.audit_store.prefix,
        schema=pg.audit_store.schema,
    )
    try:
        with pytest.raises(RuntimeError, match="invalid audit runtime connection configuration"):
            create_app(
                managed_rule_store=pg.managed_rule_store,
                change_order_store=pg.change_order_store,
                resolve_identity=None,
                can_read_config=lambda _: False,
                auth_store=pg.auth_store,
                audit_store=owner_audit_store,
                audit_resource_hmac_key=_AUDIT_RESOURCE_HMAC_KEY,
            )
    finally:
        pg.connection.rollback()
        cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(pg.runtime_role)))
        cursor.execute("SELECT current_user")
        assert cursor.fetchone()[0] == pg.runtime_role
        pg.connection.commit()

    assert _app(pg) is not None


def _audit_events(pg: PgHarness) -> tuple[Any, ...]:
    events = pg.audit_store.list_events()
    pg.connection.rollback()
    return events


def _only_new_audit_event(pg: PgHarness, previous_count: int) -> Any:
    events = _audit_events(pg)
    assert len(events) == previous_count + 1
    return events[-1].record


@contextmanager
def _reject_audit_appends(pg: PgHarness, constraint_name: str) -> Iterator[None]:
    from psycopg import sql

    cursor = pg.connection.cursor()
    try:
        cursor.execute("RESET ROLE")
        pg.connection.commit()
        cursor.execute(
            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} CHECK (FALSE) NOT VALID").format(
                sql.SQL(pg.audit_store.qualified_table), sql.Identifier(constraint_name)
            )
        )
        pg.connection.commit()
        cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(pg.runtime_role)))
        cursor.execute("SELECT current_user")
        assert cursor.fetchone()[0] == pg.runtime_role
        pg.connection.commit()
        yield
    finally:
        pg.connection.rollback()
        cursor.execute("RESET ROLE")
        pg.connection.commit()
        try:
            cursor.execute(
                sql.SQL("ALTER TABLE {} DROP CONSTRAINT IF EXISTS {}").format(
                    sql.SQL(pg.audit_store.qualified_table), sql.Identifier(constraint_name)
                )
            )
            pg.connection.commit()
        finally:
            try:
                cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(pg.runtime_role)))
                cursor.execute("SELECT current_user")
                assert cursor.fetchone()[0] == pg.runtime_role
                pg.connection.commit()
            finally:
                cursor.close()


def test_api_persists_allowed_and_denied_events_with_redacted_snapshots(pg: PgHarness) -> None:
    _bootstrap(pg)
    pg.auth_store.create_user("operator-1", "operator-password-long", {Role.OPERATOR}, pg.clock[0])
    admin = TestClient(_app(pg), base_url="https://testserver")

    event_count = len(_audit_events(pg))
    login_csrf = _login(admin, "admin-1", "admin-password-long")
    login_session_token = admin.cookies.get("__Host-as_console_session")
    assert login_session_token is not None
    login_event = _only_new_audit_event(pg, event_count)
    assert (login_event.actor, login_event.outcome) == ("admin-1", AuditOutcome.ALLOWED)
    assert login_event.before_value is None
    assert login_event.after_value == {
        "user_id": "admin-1",
        "created_at": _NOW,
        "expires_at": _NOW + 28_800,
    }

    event_count = len(_audit_events(pg))
    failed_login = admin.post(
        "/internal/v1/auth/login",
        json={"user_id": "admin-1", "password": "incorrect-password"},
    )
    failed_login_event = _only_new_audit_event(pg, event_count)
    assert failed_login.status_code == 401
    assert (failed_login_event.actor, failed_login_event.outcome) == (
        "anonymous",
        AuditOutcome.DENIED,
    )
    assert failed_login_event.before_value is failed_login_event.after_value is None

    for path in ("/internal/v1/auth/session", "/internal/v1/managed-rules"):
        event_count = len(_audit_events(pg))
        response = admin.get(path)
        read_event = _only_new_audit_event(pg, event_count)
        assert response.status_code == 200
        assert (read_event.actor, read_event.outcome) == ("admin-1", AuditOutcome.ALLOWED)
        assert read_event.before_value is read_event.after_value is None

    csrf = admin.cookies.get("__Host-as_console_csrf")
    assert csrf is not None
    event_count = len(_audit_events(pg))
    created_user = admin.post(
        "/internal/v1/auth/users",
        json={"user_id": "viewer-audit", "password": "viewer-password-long", "roles": ["viewer"]},
        headers={"X-CSRF-Token": csrf},
    )
    create_event = _only_new_audit_event(pg, event_count)
    assert created_user.status_code == 201
    assert (create_event.actor, create_event.outcome) == ("admin-1", AuditOutcome.ALLOWED)
    assert create_event.before_value is None
    assert create_event.after_value == created_user.json()

    event_count = len(_audit_events(pg))
    changed_password = admin.patch(
        "/internal/v1/auth/users/viewer-audit",
        json={"password": "viewer-password-updated"},
        headers={"X-CSRF-Token": csrf},
    )
    password_event = _only_new_audit_event(pg, event_count)
    assert changed_password.status_code == 200
    assert password_event.before_value["user_id"] == "viewer-audit"
    assert password_event.after_value == changed_password.json()
    assert "viewer-password" not in json.dumps(
        (password_event.before_value, password_event.after_value)
    )
    assert "verifier" not in json.dumps((password_event.before_value, password_event.after_value))

    event_count = len(_audit_events(pg))
    csrf_denied = admin.post("/internal/v1/auth/users", json={})
    csrf_event = _only_new_audit_event(pg, event_count)
    assert csrf_denied.status_code == 403
    assert (csrf_event.actor, csrf_event.outcome) == ("admin-1", AuditOutcome.DENIED)
    assert csrf_event.before_value is csrf_event.after_value is None

    viewer = TestClient(_app(pg), base_url="https://testserver")
    viewer_csrf = _login(viewer, "viewer-audit", "viewer-password-updated")
    event_count = len(_audit_events(pg))
    role_denied = viewer.post(
        "/internal/v1/change-orders",
        json=_change_order_payload(),
        headers={"X-CSRF-Token": viewer_csrf},
    )
    role_event = _only_new_audit_event(pg, event_count)
    assert role_denied.status_code == 403
    assert (role_event.actor, role_event.outcome) == ("viewer-audit", AuditOutcome.DENIED)
    assert role_event.before_value is role_event.after_value is None

    event_count = len(_audit_events(pg))
    created_order = admin.post(
        "/internal/v1/change-orders",
        json=_change_order_payload(),
        headers={"X-CSRF-Token": csrf},
    )
    order_event = _only_new_audit_event(pg, event_count)
    assert created_order.status_code == 201
    assert (order_event.actor, order_event.outcome) == ("admin-1", AuditOutcome.ALLOWED)
    assert order_event.before_value is None
    assert order_event.after_value == created_order.json()

    event_count = len(_audit_events(pg))
    logged_out = admin.post("/internal/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    logout_event = _only_new_audit_event(pg, event_count)
    assert logged_out.status_code == 204
    assert (logout_event.actor, logout_event.outcome) == ("admin-1", AuditOutcome.ALLOWED)
    assert logout_event.before_value == {
        "user_id": "admin-1",
        "created_at": _NOW,
        "expires_at": _NOW + 28_800,
        "revoked_at": None,
    }
    assert logout_event.after_value == {
        "user_id": "admin-1",
        "created_at": _NOW,
        "expires_at": _NOW + 28_800,
        "revoked_at": _NOW,
    }

    replay_cookies = {
        "__Host-as_console_session": login_session_token,
        "__Host-as_console_csrf": login_csrf,
    }
    for name, value in replay_cookies.items():
        admin.cookies.set(name, value)
    event_count = len(_audit_events(pg))
    replayed_logout = admin.post(
        "/internal/v1/auth/logout",
        headers={"X-CSRF-Token": login_csrf},
    )
    replay_event = _only_new_audit_event(pg, event_count)
    assert replayed_logout.status_code == 401
    assert replay_event.outcome is AuditOutcome.DENIED
    assert replay_event.before_value is replay_event.after_value is None

    event_count = len(_audit_events(pg))
    invalid_session = TestClient(_app(pg), base_url="https://testserver").get(
        "/internal/v1/managed-rules",
        cookies={"__Host-as_console_session": "invalid-session-token"},
    )
    invalid_session_event = _only_new_audit_event(pg, event_count)
    assert invalid_session.status_code == 401
    assert (invalid_session_event.actor, invalid_session_event.outcome) == (
        "anonymous",
        AuditOutcome.DENIED,
    )
    assert invalid_session_event.before_value is invalid_session_event.after_value is None

    events = _audit_events(pg)
    serialized_events = json.dumps(
        [
            (
                event.record.actor,
                event.record.action,
                event.record.resource,
                event.record.before_value,
                event.record.after_value,
            )
            for event in events
        ]
    )
    for secret in (
        "admin-password-long",
        "incorrect-password",
        "viewer-password-long",
        "viewer-password-updated",
        "invalid-session-token",
        "password_verifier",
        login_session_token,
        login_csrf,
    ):
        assert secret not in serialized_events


def test_token_shaped_path_parameter_is_hashed_in_persisted_audit_resource(pg: PgHarness) -> None:
    _bootstrap(pg)
    client = TestClient(_app(pg), base_url="https://testserver")
    _login(client, "admin-1", "admin-password-long")
    token_like_id = "A" * 43
    path = f"/internal/v1/change-orders/{token_like_id}"
    route_template = "/internal/v1/change-orders/{change_id}"
    expected_digest = hmac.new(
        _AUDIT_RESOURCE_HMAC_KEY, token_like_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    expected_resource = f"{route_template} change_id#{expected_digest}"

    for _ in range(2):
        previous_count = len(_audit_events(pg))
        response = client.get(path)
        record = _only_new_audit_event(pg, previous_count)

        assert response.status_code == 404
        assert token_like_id not in record.resource
        assert path not in record.resource
        assert route_template in record.resource
        assert record.resource == expected_resource


def test_unknown_options_and_trace_are_session_authenticated_and_audited(pg: PgHarness) -> None:
    _bootstrap(pg)
    client = TestClient(_app(pg), base_url="https://testserver")
    csrf = _login(client, "admin-1", "admin-password-long")

    for method, token_like_id, expected_status, headers in (
        ("OPTIONS", "C" * 43, 403, {}),
        ("TRACE", "D" * 43, 404, {"X-CSRF-Token": csrf}),
        ("CONNECT", "E" * 43, 404, {"X-CSRF-Token": csrf}),
    ):
        unmatched_path = f"config/export/{token_like_id}/unknown"
        path = f"/internal/v1/{unmatched_path}"
        expected_digest = hmac.new(
            _AUDIT_RESOURCE_HMAC_KEY, unmatched_path.encode(), hashlib.sha256
        ).hexdigest()
        expected_resource = f"/internal/v1/{{unmatched_path:path}} unmatched_path#{expected_digest}"
        previous_count = len(_audit_events(pg))

        response = client.request(method, path, headers=headers)
        record = _only_new_audit_event(pg, previous_count)

        assert response.status_code == expected_status
        assert (record.actor, record.outcome) == ("admin-1", AuditOutcome.DENIED)
        assert record.action == f"{method} /internal/v1/{{unmatched_path:path}}"
        assert record.resource == expected_resource
        assert token_like_id not in record.resource
        assert path not in record.resource


def test_login_and_session_creation_roll_back_when_audit_append_fails(pg: PgHarness) -> None:
    from psycopg.pq import TransactionStatus

    _bootstrap(pg)
    client = TestClient(_app(pg), base_url="https://testserver")
    before_events = len(_audit_events(pg))

    with _reject_audit_appends(pg, "reject_login_audit"):
        response = client.post(
            "/internal/v1/auth/login",
            json={"user_id": "admin-1", "password": "admin-password-long"},
        )

        assert response.status_code == 500
        assert response.json() == {"detail": "audit service unavailable"}
        assert client.cookies.get("__Host-as_console_session") is None
        assert client.cookies.get("__Host-as_console_csrf") is None

        cursor = pg.connection.cursor()
        cursor.execute(
            f"SELECT COUNT(*), COUNT(*) FILTER (WHERE revoked_at IS NULL) "
            f"FROM {pg.auth_store.sessions_table} WHERE user_id = %s",
            ("admin-1",),
        )
        assert cursor.fetchone() == (0, 0)
        pg.connection.rollback()
        assert len(_audit_events(pg)) == before_events
        assert pg.connection.info.transaction_status is TransactionStatus.IDLE


def test_logout_and_session_revocation_roll_back_when_audit_append_fails(pg: PgHarness) -> None:
    from psycopg.pq import TransactionStatus

    _bootstrap(pg)
    client = TestClient(_app(pg), base_url="https://testserver")
    csrf = _login(client, "admin-1", "admin-password-long")
    session_token = client.cookies.get("__Host-as_console_session")
    assert session_token is not None
    csrf_cookie = client.cookies.get("__Host-as_console_csrf")
    assert csrf_cookie is not None
    before_events = len(_audit_events(pg))

    with _reject_audit_appends(pg, "reject_logout_audit"):
        assert pg.auth_store.resolve_session(session_token, pg.clock[0]) is not None
        pg.connection.rollback()
        response = client.post(
            "/internal/v1/auth/logout",
            headers={"X-CSRF-Token": csrf},
        )

        assert response.status_code == 500
        assert response.json() == {"detail": "audit service unavailable"}
        assert client.cookies.get("__Host-as_console_session") == session_token
        assert client.cookies.get("__Host-as_console_csrf") == csrf_cookie
        assert pg.auth_store.resolve_session(session_token, pg.clock[0]) is not None
        pg.connection.rollback()
        assert len(_audit_events(pg)) == before_events
        assert pg.connection.info.transaction_status is TransactionStatus.IDLE


def test_change_order_and_audit_commit_atomically_and_audit_failure_rolls_back(
    pg: PgHarness,
) -> None:
    _bootstrap(pg)
    client = TestClient(_app(pg), base_url="https://testserver")
    csrf = _login(client, "admin-1", "admin-password-long")
    initial_events = len(_audit_events(pg))
    initial_orders = pg.change_order_store.list_latest()
    pg.connection.commit()

    created = client.post(
        "/internal/v1/change-orders",
        json=_change_order_payload(),
        headers={"X-CSRF-Token": csrf},
    )
    event = _only_new_audit_event(pg, initial_events)
    assert created.status_code == 201
    assert event.outcome is AuditOutcome.ALLOWED
    assert event.before_value is None
    assert event.after_value == created.json()
    order_id = created.json()["record"]["order"]["change_id"]
    assert pg.change_order_store.get(order_id) is not None
    pg.connection.rollback()

    from psycopg import sql

    cursor = pg.connection.cursor()
    cursor.execute("RESET ROLE")
    pg.connection.commit()
    try:
        cursor.execute(
            f"ALTER TABLE {pg.audit_store.qualified_table} "
            "ADD CONSTRAINT reject_change_order_audit "
            "CHECK (FALSE) NOT VALID"
        )
        pg.connection.commit()
        with pytest.raises(pg.driver.errors.CheckViolation):
            cursor.execute(
                f"INSERT INTO {pg.audit_store.qualified_table} "
                "(actor, action, resource, outcome, occurred_at) "
                "VALUES ('probe', 'probe', '/probe', 'allowed', 1700000000)"
            )
        pg.connection.rollback()
        before_failed_audit = len(_audit_events(pg))
        orders_before_failure = pg.change_order_store.list_latest()
        pg.connection.commit()

        cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(pg.runtime_role)))
        cursor.execute("SELECT current_user")
        assert cursor.fetchone()[0] == pg.runtime_role
        pg.connection.commit()
        rejected = client.post(
            "/internal/v1/change-orders",
            json=_change_order_payload(),
            headers={"X-CSRF-Token": csrf},
        )

        assert rejected.status_code == 500, (
            rejected.status_code,
            len(_audit_events(pg)),
            before_failed_audit,
        )
        assert rejected.json() == {"detail": "audit service unavailable"}
        assert len(_audit_events(pg)) == before_failed_audit
        assert pg.change_order_store.list_latest() == orders_before_failure
        assert len(initial_orders) == 0
    finally:
        pg.connection.rollback()
        cursor.execute("RESET ROLE")
        pg.connection.commit()


def test_response_validation_failure_rolls_back_change_order_and_nulls_denied_snapshots(
    pg: PgHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from psycopg.pq import TransactionStatus

    _bootstrap(pg)
    client = TestClient(_app(pg), base_url="https://testserver", raise_server_exceptions=False)
    csrf = _login(client, "admin-1", "admin-password-long")
    before_events = len(_audit_events(pg))
    assert pg.change_order_store.list_latest() == ()
    pg.connection.rollback()

    with monkeypatch.context() as patcher:
        patcher.setattr(api_module, "_change_order_response", lambda _: {"invalid": True})
        response = client.post(
            "/internal/v1/change-orders",
            json=_change_order_payload(),
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 500
    assert pg.connection.info.transaction_status is TransactionStatus.IDLE
    assert pg.change_order_store.list_latest() == ()
    pg.connection.rollback()

    event = _only_new_audit_event(pg, before_events)
    assert event.outcome is AuditOutcome.DENIED
    assert event.before_value is event.after_value is None


def test_login_session_protected_reads_and_csrf_change_order_write(pg: PgHarness) -> None:
    _bootstrap(pg)
    pg.auth_store.create_user("operator-1", "operator-password-long", {Role.OPERATOR}, pg.clock[0])
    client = TestClient(_app(pg), base_url="https://testserver")
    _login(client, "admin-1", "admin-password-long")
    session_cookie = client.cookies.get("__Host-as_console_session")
    assert session_cookie is not None
    response_headers = client.post(
        "/internal/v1/auth/login",
        json={"user_id": "admin-1", "password": "admin-password-long"},
    )
    set_cookie = response_headers.headers.get_list("set-cookie")
    assert len(set_cookie) == 2
    session_header = next(value for value in set_cookie if "__Host-as_console_session=" in value)
    csrf_header = next(value for value in set_cookie if "__Host-as_console_csrf=" in value)
    assert all(
        flag in session_header for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/")
    )
    assert all(flag in csrf_header for flag in ("Secure", "SameSite=strict", "Path=/"))
    assert "HttpOnly" not in csrf_header
    assert "Domain=" not in session_header + csrf_header

    session = client.get("/internal/v1/auth/session")
    protected = client.get("/internal/v1/managed-rules")
    assert session.status_code == protected.status_code == 200
    assert session.json() == {"user_id": "admin-1", "roles": ["admin"]}

    unauthenticated = TestClient(_app(pg), base_url="https://testserver").get(
        "/internal/v1/managed-rules"
    )
    assert unauthenticated.status_code == 401

    operator = TestClient(_app(pg), base_url="https://testserver")
    operator_csrf = _login(operator, "operator-1", "operator-password-long")
    operator_cookies = {
        "__Host-as_console_session": operator.cookies.get("__Host-as_console_session"),
    }
    missing = TestClient(_app(pg), base_url="https://testserver")
    missing.cookies.set("__Host-as_console_session", operator_cookies["__Host-as_console_session"])
    csrf_missing = missing.post("/internal/v1/change-orders", json=_change_order_payload())
    mismatch = operator.post(
        "/internal/v1/change-orders",
        json=_change_order_payload(),
        headers={"X-CSRF-Token": "mismatched-csrf-token"},
    )
    assert csrf_missing.status_code == mismatch.status_code == 403
    created = operator.post(
        "/internal/v1/change-orders",
        json=_change_order_payload(),
        headers={"X-CSRF-Token": operator_csrf},
    )
    assert created.status_code == 201, created.text


def test_session_roles_are_current_and_viewer_cannot_submit(pg: PgHarness) -> None:
    _bootstrap(pg)
    pg.auth_store.create_user("viewer-1", "viewer-password-long", {Role.VIEWER}, pg.clock[0])
    client = TestClient(_app(pg), base_url="https://testserver")
    csrf = _login(client, "viewer-1", "viewer-password-long")

    session = client.get("/internal/v1/auth/session")
    read = client.get("/internal/v1/managed-rules")
    denied = client.post(
        "/internal/v1/change-orders",
        json=_change_order_payload(),
        headers={"X-CSRF-Token": csrf},
    )

    assert session.json() == {"user_id": "viewer-1", "roles": ["viewer"]}
    assert read.status_code == 200
    assert denied.status_code == 403


def test_logout_revokes_only_current_session_and_clears_both_cookies(pg: PgHarness) -> None:
    _bootstrap(pg)
    first = TestClient(_app(pg), base_url="https://testserver")
    first_csrf = _login(first, "admin-1", "admin-password-long")
    first_cookies = {
        "__Host-as_console_session": first.cookies.get("__Host-as_console_session"),
        "__Host-as_console_csrf": first_csrf,
    }
    second = TestClient(_app(pg), base_url="https://testserver")
    second_csrf = _login(second, "admin-1", "admin-password-long")

    logout = second.post(
        "/internal/v1/auth/logout",
        headers={"X-CSRF-Token": second_csrf},
    )
    still_active = TestClient(_app(pg), base_url="https://testserver").get(
        "/internal/v1/auth/session", cookies=first_cookies
    )
    revoked = second.get("/internal/v1/auth/session")

    assert logout.status_code == 204
    assert still_active.status_code == 200
    assert revoked.status_code == 401
    cleared = logout.headers.get_list("set-cookie")
    assert len(cleared) == 2
    assert all("Max-Age=0" in value and "Path=/" in value for value in cleared)
    assert all("Secure" in value and "SameSite=strict" in value for value in cleared)


def test_admin_user_updates_revoke_sessions_and_never_return_verifiers(pg: PgHarness) -> None:
    _bootstrap(pg)
    pg.auth_store.create_user("operator-1", "operator-password-long", {Role.OPERATOR}, pg.clock[0])
    admin = TestClient(_app(pg), base_url="https://testserver")
    admin_csrf = _login(admin, "admin-1", "admin-password-long")
    users = admin.get("/internal/v1/auth/users")
    assert users.status_code == 200
    assert all("password_verifier" not in user and "verifier" not in user for user in users.json())
    created_user = admin.post(
        "/internal/v1/auth/users",
        json={
            "user_id": "viewer-created",
            "password": "viewer-created-password",
            "roles": ["viewer"],
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert created_user.status_code == 201, created_user.text
    assert "viewer-created-password" not in created_user.text
    assert "password_verifier" not in created_user.json()

    operator = TestClient(_app(pg), base_url="https://testserver")
    _login(operator, "operator-1", "operator-password-long")
    role_change = admin.patch(
        "/internal/v1/auth/users/operator-1",
        json={"roles": ["viewer"]},
        headers={"X-CSRF-Token": admin_csrf},
    )
    stale_role_session = operator.get("/internal/v1/auth/session")
    assert role_change.status_code == 200
    assert stale_role_session.status_code == 401

    operator = TestClient(_app(pg), base_url="https://testserver")
    _login(operator, "operator-1", "operator-password-long")
    password_change = admin.patch(
        "/internal/v1/auth/users/operator-1",
        json={"password": "operator-password-updated"},
        headers={"X-CSRF-Token": admin_csrf},
    )
    stale_password_session = operator.get("/internal/v1/auth/session")
    assert password_change.status_code == 200
    assert stale_password_session.status_code == 401

    operator = TestClient(_app(pg), base_url="https://testserver")
    _login(operator, "operator-1", "operator-password-updated")
    disable = admin.patch(
        "/internal/v1/auth/users/operator-1",
        json={"enabled": False},
        headers={"X-CSRF-Token": admin_csrf},
    )
    stale_disabled_session = operator.get("/internal/v1/auth/session")
    assert disable.status_code == 200
    assert stale_disabled_session.status_code == 401


def test_invalid_and_expired_session_never_fall_back_to_callback(pg: PgHarness) -> None:
    _bootstrap(pg)
    expired = pg.auth_store.create_session("admin-1", pg.clock[0])
    callback_calls = 0

    def callback(request: Request) -> ApiIdentity | None:
        nonlocal callback_calls
        callback_calls += 1
        return None

    client = TestClient(_app(pg, callback), base_url="https://testserver")
    invalid = client.get(
        "/internal/v1/managed-rules",
        cookies={"__Host-as_console_session": "invalid"},
    )
    pg.clock[0] += 28_800
    expired_response = client.get(
        "/internal/v1/managed-rules",
        cookies={"__Host-as_console_session": expired.token},
    )

    assert invalid.status_code == expired_response.status_code == 401
    assert callback_calls == 0


def test_unknown_internal_paths_persist_denied_events_and_require_csrf(pg: PgHarness) -> None:
    _bootstrap(pg)
    client = TestClient(_app(pg), base_url="https://testserver")
    csrf = _login(client, "admin-1", "admin-password-long")
    token_like_id = "A" * 43
    unmatched_path = f"config/export/{token_like_id}/unknown"
    path = f"/internal/v1/{unmatched_path}"

    event_count = len(_audit_events(pg))
    read = client.get(path)
    read_event = _only_new_audit_event(pg, event_count)
    expected_digest = hmac.new(
        _AUDIT_RESOURCE_HMAC_KEY, unmatched_path.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert read.status_code == 404
    assert (read_event.actor, read_event.outcome) == ("admin-1", AuditOutcome.DENIED)
    assert read_event.action == "GET /internal/v1/{unmatched_path:path}"
    assert read_event.resource == (
        f"/internal/v1/{{unmatched_path:path}} unmatched_path#{expected_digest}"
    )
    assert token_like_id not in read_event.resource
    assert path not in read_event.resource

    event_count = len(_audit_events(pg))
    missing_csrf = client.post(path)
    missing_csrf_event = _only_new_audit_event(pg, event_count)
    assert missing_csrf.status_code == 403
    assert (missing_csrf_event.actor, missing_csrf_event.outcome) == (
        "admin-1",
        AuditOutcome.DENIED,
    )

    event_count = len(_audit_events(pg))
    valid_csrf = client.post(path, headers={"X-CSRF-Token": csrf})
    valid_csrf_event = _only_new_audit_event(pg, event_count)
    assert valid_csrf.status_code == 404
    assert (valid_csrf_event.actor, valid_csrf_event.outcome) == (
        "admin-1",
        AuditOutcome.DENIED,
    )


def test_last_enabled_admin_cannot_be_demoted_or_disabled(pg: PgHarness) -> None:
    _bootstrap(pg)
    admin = TestClient(_app(pg), base_url="https://testserver")
    csrf = _login(admin, "admin-1", "admin-password-long")

    demote = admin.patch(
        "/internal/v1/auth/users/admin-1",
        json={"roles": ["viewer"]},
        headers={"X-CSRF-Token": csrf},
    )
    disable = admin.patch(
        "/internal/v1/auth/users/admin-1",
        json={"enabled": False},
        headers={"X-CSRF-Token": csrf},
    )

    assert demote.status_code == disable.status_code == 409
    assert pg.auth_store.get_user("admin-1").enabled is True
    assert pg.auth_store.get_user("admin-1").roles == frozenset({Role.ADMIN})


def test_concurrent_admin_demotion_leaves_one_enabled_admin(pg: PgHarness) -> None:
    _bootstrap(pg)
    pg.auth_store.create_user("admin-2", "second-admin-password", {Role.ADMIN}, pg.clock[0])
    connections = [
        pg.driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS) for _ in range(2)
    ]
    stores = [
        PostgresConsoleAuthStore(connection, prefix=pg.auth_store.prefix, schema=pg.schema)
        for connection in connections
    ]
    barrier = threading.Barrier(2)

    def demote(index: int) -> bool:
        barrier.wait(timeout=8)
        try:
            stores[index].update_user(f"admin-{index + 1}", pg.clock[0] + 1, roles={Role.VIEWER})
            return True
        except LastEnabledConsoleAdminError:
            return False

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = tuple(pool.map(demote, range(2)))
    finally:
        for connection in connections:
            connection.close()

    assert sorted(outcomes) == [False, True]
    assert (
        sum(user.enabled and Role.ADMIN in user.roles for user in pg.auth_store.list_users()) == 1
    )
