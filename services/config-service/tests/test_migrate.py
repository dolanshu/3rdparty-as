"""Unit coverage for owner-only database schema provisioning."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import pytest
from psycopg import sql

from as_config_service import migrate

pytestmark = pytest.mark.unit

_MANAGED_GUARD = f"as_managed_rule_events_immutable_{sha256(b'managed_rules').hexdigest()[:12]}"


def _environment() -> dict[str, str]:
    return {
        "AS_CONFIG_OWNER_DSN": "postgresql://owner:local-test-only@localhost/config",
        "AS_CONFIG_RUNTIME_ROLE": "as_config_runtime",
    }


def _render(query: Any) -> str:
    if isinstance(query, sql.Composable):
        return query.as_string()
    return str(query)


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.closed = False

    def execute(self, query: Any, params: tuple[object, ...] = ()) -> None:
        self.connection.statements.append((_render(query), params))
        if self.connection.fail_execute:
            raise RuntimeError("database failure")

    def fetchone(self) -> tuple[Any, ...] | None:
        statement = self.connection.statements[-1][0]
        if statement == "SELECT current_user":
            return ("config_owner",)
        if "pg_get_userbyid(n.nspowner)" in statement:
            return ("config_owner",)
        return None

    def fetchall(self) -> list[tuple[Any, ...]]:
        statement = self.connection.statements[-1][0]
        if "pg_attribute" in statement:
            if self.connection.column_rows is not None:
                return self.connection.column_rows
            if self.connection.ensured_stores >= 6:
                column_map = migrate._config_table_column_map("as_config")
                return [
                    (table, column, "config_owner")
                    for table, columns in column_map.items()
                    for column in columns
                ]
            return []
        if "pg_proc" in statement:
            if self.connection.routine_rows is not None:
                return self.connection.routine_rows
            return [
                (name, "f", 0, "trigger", "config_owner", False)
                for name in sorted(self.connection.expected_routines)
            ]
        if "pg_class" in statement:
            if self.connection.relation_rows is not None:
                return self.connection.relation_rows
            if self.connection.ensured_stores >= 6:
                return [
                    (table, "r", "config_owner")
                    for table in migrate._config_table_column_map("as_config")
                ]
        return []

    def close(self) -> None:
        self.closed = True


class _Connection:
    def __init__(
        self,
        *,
        fail_execute: bool = False,
        relation_rows: list[tuple[Any, ...]] | None = None,
        routine_rows: list[tuple[Any, ...]] | None = None,
        column_rows: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.fail_execute = fail_execute
        self.relation_rows = relation_rows
        self.routine_rows = routine_rows
        self.column_rows = column_rows
        self.expected_routines: set[str] = set()
        self.ensured_stores = 0
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def _install_fake_stores(
    monkeypatch: pytest.MonkeyPatch, connection: _Connection
) -> list[tuple[str, str | None]]:
    events: list[tuple[str, str | None]] = []

    class _Store:
        def __init__(self, _connection: Any, *, schema: str, name: str) -> None:
            assert isinstance(_connection, migrate._OwnerMigrationConnection)
            assert _connection._connection is connection
            assert schema == "as_config"
            self.name = name
            prefixes = {
                "PostgresManagedRuleStore": (
                    "managed_rules",
                    "as_managed_rule_events_immutable",
                    "as_managed_rule_head_revision",
                    "as_managed_rule_event_head",
                ),
                "PostgresChangeOrderStore": (
                    "change_orders",
                    "as_change_order_events_immutable",
                    "as_change_order_head_revision",
                    "as_change_order_event_head",
                ),
                "PostgresDistributionStore": (
                    "distributions",
                    "as_distribution_events_immutable",
                    "as_distribution_heads_revision",
                    "as_distribution_events_head",
                ),
            }
            if name in prefixes:
                prefix, guard, head, event = prefixes[name]
                prefix_hash = sha256(prefix.encode()).hexdigest()[:12]
                self.guard_function = f'"{schema}"."{guard}_{prefix_hash}"'
                self.head_revision_function = f'"{schema}"."{head}_{prefix_hash}"'
                self.event_head_function = f'"{schema}"."{event}_{prefix_hash}"'
                connection.expected_routines.update(
                    (
                        self.guard_function.rsplit(".", 1)[1].strip('"'),
                        self.head_revision_function.rsplit(".", 1)[1].strip('"'),
                        self.event_head_function.rsplit(".", 1)[1].strip('"'),
                    )
                )
            self._connection = _connection

        def ensure_schema(self) -> None:
            assert connection.commits == 0
            self._connection.commit()
            connection.ensured_stores += 1
            events.append((self.name, None))

    for name in (
        "PostgresManagedRuleStore",
        "PostgresChangeOrderStore",
        "PostgresDistributionStore",
        "PostgresConsoleAuthStore",
        "PostgresAsInstanceStore",
    ):

        def factory(
            connection_arg: _Connection,
            *,
            _name: str = name,
            **kwargs: Any,
        ) -> _Store:
            return _Store(connection_arg, name=_name, **kwargs)

        monkeypatch.setattr(migrate, name, factory)

    class _AuditStore:
        def __init__(self, _connection: Any, *, schema: str) -> None:
            assert isinstance(_connection, migrate._OwnerMigrationConnection)
            assert _connection._connection is connection
            assert schema == "console_audit"
            self._connection = _connection

        def ensure_schema(self, runtime_role: str) -> None:
            assert connection.commits == 0
            self._connection.commit()
            events.append(("PostgresAuditStore", runtime_role))

    class _VersionStore:
        def __init__(self, _connection: Any, *, table: str) -> None:
            assert isinstance(_connection, migrate._OwnerMigrationConnection)
            assert _connection._connection is connection
            assert table == "as_config_config_versions"
            self._connection = _connection

        def ensure_schema(self) -> None:
            assert connection.commits == 0
            self._connection.commit()
            connection.ensured_stores += 1
            events.append(("PostgresVersionStore", None))

    monkeypatch.setattr(migrate, "PostgresVersionStore", _VersionStore)
    monkeypatch.setattr(migrate, "PostgresAuditStore", _AuditStore)
    return events


@pytest.mark.parametrize(
    "environment",
    (
        {},
        {"AS_CONFIG_OWNER_DSN": "postgresql://owner:sentinel host='unterminated"},
        {"AS_CONFIG_OWNER_DSN": "postgresql://owner@localhost/config"},
    ),
)
def test_invalid_configuration_fails_before_connecting(
    environment: dict[str, str],
) -> None:
    connect_calls = 0

    def connect(_dsn: str) -> _Connection:
        nonlocal connect_calls
        connect_calls += 1
        raise AssertionError("invalid configuration must fail before connecting")

    with pytest.raises(ValueError):
        config = migrate.load_migration_config(environment)
        migrate.migrate_database(config, connect=connect)
    assert connect_calls == 0


@pytest.mark.parametrize(
    ("config_schema", "audit_schema"),
    (("public", "console_audit"), ("as_config", "as_config")),
)
def test_public_or_equal_schemas_are_rejected_before_connecting(
    config_schema: str,
    audit_schema: str,
) -> None:
    environment = _environment()
    environment["AS_CONFIG_SCHEMA"] = config_schema
    environment["AS_AUDIT_SCHEMA"] = audit_schema
    connect_calls = 0

    def connect(_dsn: str) -> _Connection:
        nonlocal connect_calls
        connect_calls += 1
        raise AssertionError("unsafe schema configuration must fail before connecting")

    with pytest.raises(ValueError):
        config = migrate.load_migration_config(environment)
        migrate.migrate_database(config, connect=connect)
    assert connect_calls == 0


def test_schema_ensure_order_and_exact_runtime_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    store_events = _install_fake_stores(monkeypatch, connection)
    config = migrate.load_migration_config(_environment())

    migrate.migrate_database(config, connect=lambda _dsn: connection)

    assert store_events == [
        ("PostgresManagedRuleStore", None),
        ("PostgresChangeOrderStore", None),
        ("PostgresDistributionStore", None),
        ("PostgresConsoleAuthStore", None),
        ("PostgresAsInstanceStore", None),
        ("PostgresVersionStore", None),
        ("PostgresAuditStore", "as_config_runtime"),
    ]
    statements = [statement for statement, _params in connection.statements]
    assert statements[:3] == [
        "SELECT current_user",
        'CREATE SCHEMA IF NOT EXISTS "as_config"',
        "SELECT pg_catalog.pg_get_userbyid(n.nspowner) FROM pg_catalog.pg_namespace n "
        "WHERE n.nspname = %s",
    ]
    grants = [statement for statement in statements if statement.startswith("GRANT ")]
    expected_grants = {
        'GRANT USAGE ON SCHEMA "as_config" TO "as_config_runtime"',
        *(
            f'GRANT SELECT, INSERT ON TABLE "as_config"."{table}" TO "as_config_runtime"'
            for table in (
                "managed_rules_heads",
                "managed_rules_events",
                "change_orders_heads",
                "change_orders_events",
                "distributions_heads",
                "distributions_events",
                "console_auth_users",
                "console_auth_sessions",
                "as_instances",
            )
        ),
        'GRANT UPDATE, DELETE ON TABLE "as_config"."as_instances" TO "as_config_runtime"',
        'GRANT SELECT, INSERT ON TABLE "as_config"."as_config_config_versions" '
        'TO "as_config_runtime"',
        'GRANT UPDATE ("current_revision") ON TABLE "as_config"."managed_rules_heads" '
        'TO "as_config_runtime"',
        'GRANT UPDATE ("latest_revision") ON TABLE "as_config"."change_orders_heads" '
        'TO "as_config_runtime"',
        'GRANT UPDATE ("latest_revision") ON TABLE "as_config"."distributions_heads" '
        'TO "as_config_runtime"',
        "GRANT UPDATE (roles_json, password_verifier, enabled, updated_at) "
        'ON TABLE "as_config".console_auth_users TO "as_config_runtime"',
        'GRANT UPDATE (revoked_at) ON TABLE "as_config".console_auth_sessions '
        'TO "as_config_runtime"',
        'GRANT SELECT ON TABLE "as_config".console_auth_bootstrap TO "as_config_runtime"',
    }
    assert set(grants) == expected_grants
    assert any("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA" in item for item in statements)
    assert any("REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA" in item for item in statements)
    assert any("REVOKE ALL PRIVILEGES ON SCHEMA" in item for item in statements)
    column_revokes = [
        statement for statement in statements if statement.startswith("REVOKE ALL PRIVILEGES (")
    ]
    version_table = migrate._version_table_name("as_config")
    assert set(column_revokes) == {
        "REVOKE ALL PRIVILEGES ("
        + ", ".join(f'"{column}"' for column in columns)
        + f') ON TABLE "as_config"."{table}" FROM PUBLIC, "as_config_runtime"'
        for table, columns in (
            *migrate._CONFIG_TABLE_COLUMNS,
            (version_table, migrate._VERSION_TABLE_COLUMNS),
        )
    }
    assert (
        'REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA "as_config" '
        'FROM PUBLIC, "as_config_runtime"'
    ) in statements
    assert (
        sum(statement.startswith("ALTER DEFAULT PRIVILEGES IN SCHEMA") for statement in statements)
        == 3
    )
    assert all(
        not any(forbidden in statement.upper() for forbidden in ("DELETE", "TRUNCATE", "CREATE"))
        for statement in grants
        if "as_instances" not in statement
    )
    assert not any(
        statement.startswith(("CREATE ROLE", "ALTER ROLE", "SET ROLE")) for statement in statements
    )
    assert connection.commits == 1
    assert connection.closed


def test_failure_rolls_back_and_closes_owner_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    events = _install_fake_stores(monkeypatch, connection)

    class FailingStore:
        def __init__(self, _connection: Any, *, schema: str) -> None:
            assert schema == "as_config"
            self._connection = _connection

        def ensure_schema(self) -> None:
            self._connection.commit()
            raise RuntimeError("database failure")

    monkeypatch.setattr(migrate, "PostgresDistributionStore", FailingStore)

    with pytest.raises(RuntimeError, match="database failure"):
        migrate.migrate_database(
            migrate.load_migration_config(_environment()), connect=lambda _dsn: connection
        )

    assert events == [
        ("PostgresManagedRuleStore", None),
        ("PostgresChangeOrderStore", None),
    ]
    assert connection.commits == 0
    assert connection.rollbacks >= 1
    assert connection.closed


@pytest.mark.parametrize(
    ("relation_rows", "routine_rows", "column_rows", "message"),
    (
        ([("unexpected_table", "r", "config_owner")], None, None, "unexpected relations"),
        ([("managed_rules_heads", "v", "config_owner")], None, None, "incompatible relation"),
        ([("managed_rules_heads", "r", "other_owner")], None, None, "owned by"),
        (
            None,
            [("unexpected_function", "f", 0, "trigger", "config_owner", False)],
            None,
            "unexpected routine",
        ),
        (
            None,
            [(_MANAGED_GUARD, "f", 0, "trigger", "other_owner", False)],
            None,
            "owned by",
        ),
        (
            None,
            [(_MANAGED_GUARD, "f", 0, "trigger", "config_owner", True)],
            None,
            "SECURITY DEFINER",
        ),
        (
            None,
            [(_MANAGED_GUARD, "f", 1, "trigger", "config_owner", False)],
            None,
            "incompatible routine",
        ),
        (
            [("managed_rules_heads", "r", "config_owner")],
            None,
            [("managed_rules_heads", "wrong_column", "config_owner")],
            "columns do not match.*shape",
        ),
        (
            [("managed_rules_heads", "r", "config_owner")],
            None,
            [("managed_rules_heads", "rule_id", "other_owner")],
            "owned by",
        ),
    ),
)
def test_catalog_rejections_roll_back_and_close(
    monkeypatch: pytest.MonkeyPatch,
    relation_rows: list[tuple[Any, ...]] | None,
    routine_rows: list[tuple[Any, ...]] | None,
    column_rows: list[tuple[Any, ...]] | None,
    message: str,
) -> None:
    connection = _Connection(
        relation_rows=relation_rows,
        routine_rows=routine_rows,
        column_rows=column_rows,
    )
    _install_fake_stores(monkeypatch, connection)

    with pytest.raises(ValueError, match=message):
        migrate.migrate_database(
            migrate.load_migration_config(_environment()), connect=lambda _dsn: connection
        )

    assert connection.commits == 0
    assert connection.rollbacks >= 1
    assert connection.closed


def test_cli_hides_dsn_from_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dsn = "postgresql://owner:dsn-sentinel@localhost/config"
    environment = _environment()
    environment["AS_CONFIG_OWNER_DSN"] = dsn
    monkeypatch.setattr(migrate.os, "environ", environment)
    monkeypatch.setattr(
        migrate.psycopg,
        "connect",
        lambda _dsn: (_ for _ in ()).throw(RuntimeError(f"failed: {dsn}")),
    )

    assert migrate.main() == 1
    output = capsys.readouterr()
    assert dsn not in output.out + output.err
    assert "dsn-sentinel" not in output.out + output.err
    assert "Config database migration failed." in output.err
