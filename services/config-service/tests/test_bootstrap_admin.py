"""Unit coverage for the one-time administrator bootstrap command."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from as_config_service import bootstrap_admin

pytestmark = pytest.mark.unit


class _Connection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Store:
    def __init__(self, connection: _Connection, *, schema: str) -> None:
        self.connection = connection
        self.schema = schema
        self.schema_ensured = False

    def ensure_schema(self) -> None:
        self.schema_ensured = True

    def bootstrap_admin(self, user_id: str, password: str, timestamp: float) -> None:
        assert user_id == "admin"
        assert password == "password"
        assert timestamp > 0


def _prepare_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    environ: dict[str, str],
    *,
    dsn: str = "postgresql://bootstrap:secret@localhost/config",
    password: str = "password",
) -> tuple[_Connection, list[tuple[_Connection, dict[str, Any], _Store]]]:
    connection = _Connection()
    stores: list[tuple[_Connection, dict[str, Any], _Store]] = []
    monkeypatch.setattr(bootstrap_admin.os, "environ", environ)
    monkeypatch.setattr("builtins.input", lambda _prompt: "admin")
    monkeypatch.setattr(bootstrap_admin.getpass, "getpass", lambda _prompt: password)

    def connect(configured_dsn: str) -> _Connection:
        assert configured_dsn == dsn
        return connection

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))

    def create_store(connection_arg: _Connection, **kwargs: Any) -> _Store:
        store = _Store(connection_arg, **kwargs)
        stores.append((connection_arg, kwargs, store))
        return store

    monkeypatch.setattr(bootstrap_admin, "PostgresConsoleAuthStore", create_store)
    return connection, stores


def test_main_passes_configured_schema_and_closes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection, stores = _prepare_bootstrap(
        monkeypatch,
        {
            "AS_CONFIG_OWNER_DSN": "postgresql://bootstrap:secret@localhost/config",
            "AS_CONFIG_SCHEMA": "as_config",
        },
    )

    assert bootstrap_admin.main() == 0

    assert len(stores) == 1
    assert stores[0][:2] == (connection, {"schema": "as_config"})
    assert stores[0][2].schema_ensured
    assert connection.closed


def test_main_defaults_schema_to_dedicated_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    connection, stores = _prepare_bootstrap(
        monkeypatch,
        {"AS_CONFIG_OWNER_DSN": "postgresql://bootstrap:secret@localhost/config"},
    )

    assert bootstrap_admin.main() == 0

    assert len(stores) == 1
    assert stores[0][:2] == (connection, {"schema": "as_config"})
    assert stores[0][2].schema_ensured
    assert connection.closed


@pytest.mark.parametrize("schema", ("bad-schema", "public"))
def test_main_rejects_invalid_schema_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
    schema: str,
) -> None:
    environ = {
        "AS_CONFIG_OWNER_DSN": "postgresql://bootstrap:secret@localhost/config",
        "AS_CONFIG_SCHEMA": schema,
    }
    monkeypatch.setattr(bootstrap_admin.os, "environ", environ)
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: pytest.fail("invalid schema must be rejected before prompting"),
    )
    connect_calls = 0

    def connect(_dsn: str) -> None:
        nonlocal connect_calls
        connect_calls += 1
        pytest.fail("invalid schema must be rejected before connecting")

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))

    assert bootstrap_admin.main() == 1
    assert connect_calls == 0


def test_main_requires_owner_dsn_before_prompting_or_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bootstrap_admin.os,
        "environ",
        {"AS_CONFIG_DSN": "postgresql://runtime:secret@localhost/config"},
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: pytest.fail("missing owner DSN must be rejected before prompting"),
    )

    def connect(_dsn: str) -> None:
        pytest.fail("missing owner DSN must be rejected before connecting")

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))

    assert bootstrap_admin.main() == 1


def test_main_closes_connection_when_bootstrap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection, _stores = _prepare_bootstrap(
        monkeypatch,
        {"AS_CONFIG_OWNER_DSN": "postgresql://bootstrap:secret@localhost/config"},
    )

    class FailingStore(_Store):
        def bootstrap_admin(self, user_id: str, password: str, timestamp: float) -> None:
            raise RuntimeError("database failure")

    monkeypatch.setattr(bootstrap_admin, "PostgresConsoleAuthStore", FailingStore)

    assert bootstrap_admin.main() == 1
    assert connection.closed


def test_main_closes_connection_and_hides_secrets_when_schema_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dsn = "postgresql://bootstrap:dsn-sentinel@localhost/config"
    password = "password-sentinel"
    connection, _stores = _prepare_bootstrap(
        monkeypatch,
        {"AS_CONFIG_OWNER_DSN": dsn},
        dsn=dsn,
        password=password,
    )

    class FailingStore(_Store):
        def ensure_schema(self) -> None:
            raise RuntimeError(f"schema failure: {dsn} {password}")

        def bootstrap_admin(self, user_id: str, password: str, timestamp: float) -> None:
            pytest.fail("bootstrap_admin must not run when ensure_schema fails")

    monkeypatch.setattr(bootstrap_admin, "PostgresConsoleAuthStore", FailingStore)

    assert bootstrap_admin.main() == 1
    assert connection.closed
    captured = capsys.readouterr()
    assert dsn not in captured.out + captured.err
    assert password not in captured.out + captured.err
