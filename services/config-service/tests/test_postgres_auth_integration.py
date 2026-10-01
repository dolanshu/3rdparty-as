"""Real-PostgreSQL coverage for console accounts and sessions. ADR-0024, REQ-S-4."""

from __future__ import annotations

import base64
import hashlib
import os
import sys
import threading
import time
import uuid
import warnings
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import pytest

import as_config_service.auth as auth_module
from as_config_service.auth import (
    BootstrapAlreadyCompleteError,
    ConsoleBootstrapRequiredError,
    DuplicateConsoleUserError,
    PostgresConsoleAuthStore,
)
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


@dataclass(frozen=True)
class PgHarness:
    store: PostgresConsoleAuthStore
    connection: Any
    driver: Any
    schema: str
    prefix: str


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
    schema = f"auth_test_{uuid.uuid4().hex[:12]}"
    prefix = f"auth_{uuid.uuid4().hex[:12]}"
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
        store = PostgresConsoleAuthStore(connection, prefix=prefix, schema=schema)
        store.ensure_schema()
        yield PgHarness(store, connection, driver, schema, prefix)
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


def _bootstrap(
    pg: PgHarness, user_id: str = "admin-1", password: str = "admin-password-long-1"
) -> None:
    pg.store.bootstrap_admin(user_id, password, _NOW)


def _create_user(pg: PgHarness, user_id: str, password: str, roles: object) -> Any:
    _bootstrap(pg)
    return pg.store.create_user(user_id, password, roles, _NOW)


def test_ensure_schema_is_idempotent_and_bootstrap_guard_is_singleton(pg: PgHarness) -> None:
    pg.store.ensure_schema()
    cursor = pg.connection.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {pg.store.bootstrap_table}")
    assert cursor.fetchone()[0] == 1
    cursor.execute(f"SELECT COUNT(*) FROM {pg.store.users_table}")
    assert cursor.fetchone()[0] == 0


def test_bootstrap_creates_first_admin_and_repeated_attempt_is_typed(pg: PgHarness) -> None:
    _bootstrap(pg)

    assert pg.store.get_user("admin-1").roles == frozenset({Role.ADMIN})
    assert pg.store.authenticate("admin-1", "admin-password-long-1").roles == frozenset(
        {Role.ADMIN}
    )
    with pytest.raises(BootstrapAlreadyCompleteError):
        _bootstrap(pg, "admin-2")


def test_bootstrap_refuses_when_any_account_already_exists(pg: PgHarness) -> None:
    cursor = pg.connection.cursor()
    cursor.execute(
        f"INSERT INTO {pg.store.users_table} "
        "(user_id, password_verifier, roles_json, enabled, created_at, updated_at) "
        "VALUES (%s, %s, %s, TRUE, %s, %s)",
        ("legacy-user", "legacy-invalid-verifier", '["viewer"]', _NOW, _NOW),
    )
    pg.connection.commit()

    with pytest.raises(BootstrapAlreadyCompleteError):
        _bootstrap(pg)


def test_create_user_requires_bootstrap_and_bootstrap_remains_available(pg: PgHarness) -> None:
    with pytest.raises(ConsoleBootstrapRequiredError):
        pg.store.create_user("ordinary-user", "ordinary-password-long", {Role.VIEWER}, _NOW)

    _bootstrap(pg)

    assert pg.store.get_user("admin-1").roles == frozenset({Role.ADMIN})


def test_concurrent_bootstrap_has_exactly_one_winner(pg: PgHarness) -> None:
    connections = [
        pg.driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS) for _ in range(2)
    ]
    stores = [
        PostgresConsoleAuthStore(connection, prefix=pg.prefix, schema=pg.schema)
        for connection in connections
    ]
    barrier = threading.Barrier(2)

    def attempt(index: int) -> bool:
        barrier.wait(timeout=8)
        try:
            stores[index].bootstrap_admin(f"admin-{index}", "parallel-bootstrap-pass", _NOW)
            return True
        except BootstrapAlreadyCompleteError:
            return False

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = tuple(pool.map(attempt, range(2)))
        assert sorted(outcomes) == [False, True]
        assert len(pg.store.list_users()) == 1
        assert pg.store.list_users()[0].roles == frozenset({Role.ADMIN})
    finally:
        for connection in connections:
            connection.close()


def test_authentication_and_session_resolve_through_a_new_store(pg: PgHarness) -> None:
    _bootstrap(pg)
    principal = pg.store.authenticate("admin-1", "admin-password-long-1")
    assert principal is not None
    assert principal.roles == frozenset({Role.ADMIN})
    session = pg.store.create_session("admin-1", _NOW)
    second_connection = pg.driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    try:
        restarted = PostgresConsoleAuthStore(second_connection, prefix=pg.prefix, schema=pg.schema)
        assert restarted.resolve_session(session.token, _NOW + 1) == principal
    finally:
        second_connection.close()


def test_expiry_explicit_revoke_role_update_and_disable_invalidate_sessions(
    pg: PgHarness,
) -> None:
    user = _create_user(pg, "operator-1", "operator-password-long", {Role.OPERATOR})
    expiring = pg.store.create_session(user.user_id, _NOW, ttl_seconds=10)
    assert pg.store.resolve_session(expiring.token, _NOW + 10) is None

    explicitly_revoked = pg.store.create_session(user.user_id, _NOW)
    assert pg.store.revoke_user_sessions(user.user_id, _NOW + 1) == 2
    assert pg.store.resolve_session(explicitly_revoked.token, _NOW + 2) is None

    role_updated = pg.store.create_session(user.user_id, _NOW + 3)
    pg.store.update_user(user.user_id, _NOW + 4, roles={Role.APPROVER})
    assert pg.store.resolve_session(role_updated.token, _NOW + 5) is None

    disabled = pg.store.create_session(user.user_id, _NOW + 6)
    pg.store.update_user(user.user_id, _NOW + 7, enabled=False)
    assert pg.store.resolve_session(disabled.token, _NOW + 8) is None


def test_session_ttl_must_be_between_one_second_and_eight_hours(pg: PgHarness) -> None:
    user = _create_user(pg, "ttl-user", "ttl-user-password-long", {Role.VIEWER})

    for ttl_seconds in (0, 28_801):
        with pytest.raises(ValueError, match="between 1 and 28800"):
            pg.store.create_session(user.user_id, _NOW, ttl_seconds=ttl_seconds)


def test_session_resolution_reads_current_roles_without_a_role_cache(pg: PgHarness) -> None:
    user = _create_user(pg, "viewer-1", "viewer-password-long", {Role.VIEWER})
    session = pg.store.create_session(user.user_id, _NOW)
    cursor = pg.connection.cursor()
    cursor.execute(
        f"UPDATE {pg.store.users_table} SET roles_json = %s WHERE user_id = %s",
        ('["approver"]', user.user_id),
    )
    pg.connection.commit()

    resolved = pg.store.resolve_session(session.token, _NOW + 1)

    assert resolved is not None
    assert resolved.roles == frozenset({Role.APPROVER})


def test_password_change_invalidates_old_password_and_sessions(pg: PgHarness) -> None:
    old_password = "operator-password-old"
    new_password = "operator-password-new"
    user = _create_user(pg, "password-user", old_password, {Role.OPERATOR})
    session = pg.store.create_session(user.user_id, _NOW)

    pg.store.update_user(user.user_id, _NOW + 1, password=new_password)

    assert pg.store.authenticate(user.user_id, old_password) is None
    assert pg.store.authenticate(user.user_id, new_password) is not None
    assert pg.store.resolve_session(session.token, _NOW + 2) is None


def test_successful_login_rehashes_a_weaker_stored_verifier(pg: PgHarness) -> None:
    password = "rehash-password-long"
    user = _create_user(pg, "rehash-user", password, {Role.VIEWER})
    salt = bytes(range(16))
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 1, 32)
    old_verifier = (
        "pbkdf2-sha256$v1$1$32$"
        f"{base64.urlsafe_b64encode(salt).decode('ascii').rstrip('=')}$"
        f"{base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')}"
    )
    cursor = pg.connection.cursor()
    cursor.execute(
        f"UPDATE {pg.store.users_table} SET password_verifier = %s WHERE user_id = %s",
        (old_verifier, user.user_id),
    )
    pg.connection.commit()

    assert pg.store.authenticate(user.user_id, password) is not None
    pg.store.create_session(user.user_id, _NOW)
    cursor.execute(
        f"SELECT password_verifier FROM {pg.store.users_table} WHERE user_id = %s",
        (user.user_id,),
    )
    assert cursor.fetchone()[0].startswith("pbkdf2-sha256$v1$600000$32$")


def test_login_lock_serializes_password_change_and_session_creation(pg: PgHarness) -> None:
    old_password = "race-password-before-change"
    new_password = "race-password-after-change"
    user = _create_user(pg, "race-user", old_password, {Role.OPERATOR})
    salt = bytes(range(16))
    digest = hashlib.pbkdf2_hmac("sha256", old_password.encode("utf-8"), salt, 1, 32)

    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    weak_verifier = f"pbkdf2-sha256$v1$1$32${encode(salt)}${encode(digest)}"
    cursor = pg.connection.cursor()
    cursor.execute(
        f"UPDATE {pg.store.users_table} SET password_verifier = %s WHERE user_id = %s",
        (weak_verifier, user.user_id),
    )
    pg.connection.commit()

    login_connection = pg.driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    mutation_connection = pg.driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    observer_connection = pg.driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    login_store = PostgresConsoleAuthStore(login_connection, prefix=pg.prefix, schema=pg.schema)
    mutation_store = PostgresConsoleAuthStore(
        mutation_connection, prefix=pg.prefix, schema=pg.schema
    )
    login_cursor = login_connection.cursor()
    login_cursor.execute("SELECT pg_backend_pid()")
    login_pid = login_cursor.fetchone()[0]
    mutation_cursor = mutation_connection.cursor()
    mutation_cursor.execute("SELECT pg_backend_pid()")
    mutation_pid = mutation_cursor.fetchone()[0]
    observer = observer_connection.cursor()
    login_locked = threading.Event()
    issue_session = threading.Event()
    mutation_started = threading.Event()
    mutation_finished = threading.Event()

    def login_and_issue_session() -> Any:
        principal = login_store.authenticate(user.user_id, old_password)
        if principal is None:
            raise AssertionError("old password should authenticate before mutation")
        login_locked.set()
        if not issue_session.wait(timeout=8):
            raise TimeoutError("session issuance was not released")
        return login_store.create_session(user.user_id, _NOW)

    def change_password() -> None:
        if not login_locked.wait(timeout=8):
            raise TimeoutError("login did not acquire its account lock")
        mutation_started.set()
        mutation_store.update_user(user.user_id, _NOW + 1, password=new_password)
        mutation_finished.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            login_future = pool.submit(login_and_issue_session)
            assert login_locked.wait(timeout=8)
            mutation_future = pool.submit(change_password)
            assert mutation_started.wait(timeout=8)

            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                observer.execute("SELECT pg_blocking_pids(%s)", (mutation_pid,))
                blockers = observer.fetchone()[0]
                if login_pid in blockers:
                    break
                if mutation_finished.is_set():
                    pytest.fail("password mutation completed before session issuance")
            else:
                pytest.fail("password mutation never waited on the login row lock")

            assert not mutation_finished.is_set()
            issue_session.set()
            session = login_future.result(timeout=8)
            mutation_future.result(timeout=8)
    finally:
        issue_session.set()
        for connection in (login_connection, mutation_connection, observer_connection):
            connection.close()

    assert pg.store.resolve_session(session.token, _NOW + 2) is None
    assert pg.store.authenticate(user.user_id, old_password) is None
    cursor.execute(
        f"SELECT password_verifier FROM {pg.store.users_table} WHERE user_id = %s",
        (user.user_id,),
    )
    final_verifier = cursor.fetchone()[0]
    assert auth_module.verify_password(new_password, final_verifier)
    assert not auth_module.verify_password(old_password, final_verifier)


def test_unknown_and_bad_password_both_return_none_after_pbkdf2_work(
    pg: PgHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_user(pg, "known-user", "known-password-long", {Role.VIEWER})
    real_pbkdf2 = hashlib.pbkdf2_hmac
    calls = 0

    def counted_pbkdf2(*args: Any, **kwargs: Any) -> bytes:
        nonlocal calls
        calls += 1
        return real_pbkdf2(*args, **kwargs)

    monkeypatch.setattr(auth_module.hashlib, "pbkdf2_hmac", counted_pbkdf2)

    assert pg.store.authenticate("known-user", "incorrect-password") is None
    assert pg.store.authenticate("unknown-user", "incorrect-password") is None
    assert calls == 2
    assert pg.store.authenticate("known-user", "é" * 513) is None
    assert pg.store.authenticate("unknown-user", "p" * 1_025) is None
    assert calls == 2


def test_csrf_requires_active_session_matching_cookie_and_header(pg: PgHarness) -> None:
    _bootstrap(pg)
    session = pg.store.create_session("admin-1", _NOW)

    assert pg.store.verify_csrf(session.token, session.csrf_token, session.csrf_token, _NOW + 1)
    assert not pg.store.verify_csrf(session.token, "A" * 43, session.csrf_token, _NOW + 1)
    assert not pg.store.verify_csrf(session.token, session.csrf_token, "B" * 43, _NOW + 1)
    assert not pg.store.verify_csrf(
        session.token, session.csrf_token, session.csrf_token, _NOW + 28_800
    )


def test_database_persists_verifier_and_token_digests_only(pg: PgHarness) -> None:
    password = "admin-password-long-1"
    _bootstrap(pg, password=password)
    session = pg.store.create_session("admin-1", _NOW)
    cursor = pg.connection.cursor()
    cursor.execute(
        f"SELECT password_verifier FROM {pg.store.users_table} WHERE user_id = %s",
        ("admin-1",),
    )
    verifier = cursor.fetchone()[0]
    cursor.execute(f"SELECT token_digest, csrf_digest FROM {pg.store.sessions_table}")
    token_digest, csrf_digest = cursor.fetchone()

    token_bytes = base64.urlsafe_b64decode(session.token + "=")
    csrf_bytes = base64.urlsafe_b64decode(session.csrf_token + "=")
    cursor.execute(f"SELECT to_jsonb(u)::text FROM {pg.store.users_table} u")
    user_row = cursor.fetchone()[0]
    cursor.execute(f"SELECT to_jsonb(s)::text FROM {pg.store.sessions_table} s")
    session_row = cursor.fetchone()[0]
    assert verifier.startswith("pbkdf2-sha256$v1$600000$32$")
    assert password not in user_row
    assert token_digest == hashlib.sha256(token_bytes).digest()
    assert csrf_digest == hashlib.sha256(csrf_bytes).digest()
    assert session.token not in session_row
    assert session.csrf_token not in session_row


def test_commit_false_rollback_leaves_no_user_or_session(pg: PgHarness) -> None:
    _bootstrap(pg)
    user = pg.store.create_user(
        "rollback-user", "rollback-user-password", {Role.VIEWER}, _NOW, commit=False
    )
    session = pg.store.create_session(user.user_id, _NOW, commit=False)
    pg.connection.rollback()

    assert pg.store.get_user(user.user_id) is None
    assert pg.store.resolve_session(session.token, _NOW + 1) is None


def test_commit_false_duplicate_error_rolls_back_entire_active_transaction(
    pg: PgHarness,
) -> None:
    user = _create_user(pg, "duplicate-user", "duplicate-user-password", {Role.VIEWER})
    staged_session = pg.store.create_session(user.user_id, _NOW, commit=False)

    with pytest.raises(DuplicateConsoleUserError):
        pg.store.create_user(
            user.user_id, "another-password-long", {Role.OPERATOR}, _NOW, commit=False
        )

    assert pg.connection.info.transaction_status.name == "IDLE"
    observer_connection = pg.driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    try:
        observer = PostgresConsoleAuthStore(observer_connection, prefix=pg.prefix, schema=pg.schema)
        assert observer.resolve_session(staged_session.token, _NOW + 1) is None
    finally:
        observer_connection.close()
