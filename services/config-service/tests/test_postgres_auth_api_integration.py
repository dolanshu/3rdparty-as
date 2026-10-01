"""Real-PostgreSQL coverage for authenticated config API flows. ADR-0024 draft."""

from __future__ import annotations

import os
import sys
import threading
import uuid
import warnings
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from as_config_service.api import ApiIdentity, create_app
from as_config_service.auth import LastEnabledConsoleAdminError, PostgresConsoleAuthStore
from as_config_service.change_order_store import PostgresChangeOrderStore
from as_config_service.managed_rule_store import PostgresManagedRuleStore
from as_console.access import Role

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


@dataclass
class PgHarness:
    connection: Any
    driver: Any
    schema: str
    auth_store: PostgresConsoleAuthStore
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
    parsed = urlparse(TEST_DSN)
    connection = None
    schema = f"auth_api_test_{uuid.uuid4().hex[:12]}"
    prefix = f"auth_api_{uuid.uuid4().hex[:10]}"
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
        cursor.execute(f'CREATE SCHEMA "{schema}"')
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
        yield PgHarness(
            connection,
            driver,
            schema,
            auth_store,
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
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
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
    )


def _bootstrap(pg: PgHarness) -> None:
    pg.auth_store.bootstrap_admin("admin-1", "admin-password-long", pg.clock[0])


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
