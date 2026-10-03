"""Owner-only PostgreSQL schema and least-privilege provisioning command."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from as_config_service.as_instance_store import PostgresAsInstanceStore
from as_config_service.audit_store import PostgresAuditStore
from as_config_service.auth import PostgresConsoleAuthStore
from as_config_service.change_order_store import PostgresChangeOrderStore
from as_config_service.distribution_store import PostgresDistributionStore
from as_config_service.managed_rule_store import PostgresManagedRuleStore
from as_config_service.postgres_store import PostgresVersionStore

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}\Z")

_VERSION_TABLE_COLUMNS = ("version", "bundle_json", "created_at", "change_id")

_CONFIG_TABLE_COLUMNS = (
    ("managed_rules_heads", ("rule_id", "current_revision")),
    (
        "managed_rules_events",
        ("rule_id", "revision", "snapshot_json", "change_id", "actor", "created_at"),
    ),
    ("change_orders_heads", ("change_id", "latest_revision")),
    ("change_orders_events", ("change_id", "revision", "snapshot_json", "audit_entry_json")),
    ("distributions_heads", ("change_id", "latest_revision")),
    ("distributions_events", ("change_id", "revision", "snapshot_json", "actor", "action")),
    (
        "console_auth_users",
        ("user_id", "password_verifier", "roles_json", "enabled", "created_at", "updated_at"),
    ),
    (
        "console_auth_sessions",
        ("token_digest", "csrf_digest", "user_id", "created_at", "expires_at", "revoked_at"),
    ),
    ("console_auth_bootstrap", ("singleton", "complete")),
    (
        "as_instances",
        (
            "instance_id",
            "use_case",
            "notify_url",
            "health_url",
            "enabled",
            "revision",
            "change_id",
            "actor",
            "updated_at",
        ),
    ),
)


def _version_table_name(config_schema: str) -> str:
    return f"{config_schema}_config_versions"


def _config_table_column_map(config_schema: str) -> dict[str, set[str]]:
    expected = {name: set(columns) for name, columns in _CONFIG_TABLE_COLUMNS}
    expected[_version_table_name(config_schema)] = set(_VERSION_TABLE_COLUMNS)
    return expected


class _Cursor(Protocol):
    def execute(self, query: Any, params: tuple[object, ...] = ()) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def close(self) -> None: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class _OwnerMigrationConnection:
    """Keep store schema setup in the owner's transaction."""

    def __init__(self, connection: _Connection) -> None:
        self._connection = connection
        self.info: Any = getattr(connection, "info", None)

    def cursor(self) -> _Cursor:
        return self._connection.cursor()

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        self._connection.rollback()


@dataclass(frozen=True)
class MigrationConfig:
    """Validated database setup settings; never reveal the owner DSN in repr."""

    owner_dsn: str = field(repr=False)
    runtime_role: str
    config_schema: str = "as_config"
    audit_schema: str = "console_audit"


def _identifier(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, default).strip()
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a valid PostgreSQL identifier")
    return value


def _validate_settings(
    owner_dsn: str,
    runtime_role: str,
    config_schema: str,
    audit_schema: str,
) -> None:
    if not owner_dsn.strip():
        raise ValueError("AS_CONFIG_OWNER_DSN must be set")
    try:
        conninfo_to_dict(owner_dsn)
    except (psycopg.Error, ValueError):
        raise ValueError(
            "AS_CONFIG_OWNER_DSN must be a valid PostgreSQL connection string"
        ) from None
    if not _IDENTIFIER.fullmatch(runtime_role):
        raise ValueError("AS_CONFIG_RUNTIME_ROLE must be a valid PostgreSQL identifier")
    if not _IDENTIFIER.fullmatch(config_schema):
        raise ValueError("AS_CONFIG_SCHEMA must be a valid PostgreSQL identifier")
    if not _IDENTIFIER.fullmatch(audit_schema):
        raise ValueError("AS_AUDIT_SCHEMA must be a valid PostgreSQL identifier")
    if config_schema == "public":
        raise ValueError("AS_CONFIG_SCHEMA must not be public")
    if audit_schema == "public":
        raise ValueError("AS_AUDIT_SCHEMA must not be public")
    if config_schema == audit_schema:
        raise ValueError("AS_CONFIG_SCHEMA and AS_AUDIT_SCHEMA must differ")


def load_migration_config(env: Mapping[str, str] | None = None) -> MigrationConfig:
    """Load required owner/runtime settings and validate them before connecting."""
    source = os.environ if env is None else env
    owner_dsn = source.get("AS_CONFIG_OWNER_DSN", "").strip()
    if not owner_dsn:
        raise ValueError("AS_CONFIG_OWNER_DSN must be set")
    runtime_role = source.get("AS_CONFIG_RUNTIME_ROLE", "").strip()
    config_schema = _identifier(source, "AS_CONFIG_SCHEMA", "as_config")
    audit_schema = _identifier(source, "AS_AUDIT_SCHEMA", "console_audit")
    _validate_settings(owner_dsn, runtime_role, config_schema, audit_schema)
    return MigrationConfig(owner_dsn, runtime_role, config_schema, audit_schema)


def _create_config_schema(connection: _Connection, schema: str) -> str:
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT current_user")
        owner_row = cursor.fetchone()
        if owner_row is None:
            raise RuntimeError("could not determine database owner identity")
        owner = str(owner_row[0])
        cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cursor.execute(
            "SELECT pg_catalog.pg_get_userbyid(n.nspowner) "
            "FROM pg_catalog.pg_namespace n WHERE n.nspname = %s",
            (schema,),
        )
        schema_owner_row = cursor.fetchone()
        if schema_owner_row is None or str(schema_owner_row[0]) != owner:
            raise ValueError("config schema must be owned by the current database role")
        return owner
    finally:
        cursor.close()


def _expected_routine_names(stores: tuple[Any, ...]) -> set[str]:
    return {
        str(function).rsplit(".", 1)[1].strip('"')
        for store in stores
        for function in (
            getattr(store, "guard_function", None),
            getattr(store, "head_revision_function", None),
            getattr(store, "event_head_function", None),
        )
        if function is not None
    }


def _validate_config_relations(
    cursor: _Cursor, schema: str, owner: str, *, require_complete: bool
) -> None:
    cursor.execute(
        "SELECT c.relname, c.relkind, pg_catalog.pg_get_userbyid(c.relowner) "
        "FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')",
        (schema,),
    )
    rows = cursor.fetchall()
    expected = set(_config_table_column_map(schema))
    actual = {str(row[0]) for row in rows}
    unexpected = actual - expected
    if unexpected:
        raise ValueError("config schema contains unexpected relations")
    if require_complete and actual != expected:
        raise ValueError("config schema is missing expected relations")
    for _name, relkind, relation_owner in rows:
        if str(relkind) != "r":
            raise ValueError("config schema contains an incompatible relation")
        if str(relation_owner) != owner:
            raise ValueError("config relation must be owned by the current database role")


def _validate_config_columns(
    cursor: _Cursor, schema: str, owner: str, *, require_complete: bool
) -> None:
    cursor.execute(
        "SELECT c.relname, a.attname, pg_catalog.pg_get_userbyid(c.relowner) "
        "FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid "
        "AND a.attnum > 0 AND NOT a.attisdropped "
        "WHERE n.nspname = %s AND c.relkind = 'r'",
        (schema,),
    )
    rows = cursor.fetchall()
    actual: dict[str, set[str]] = {}
    for relation, column, relation_owner in rows:
        relation_name = str(relation)
        actual.setdefault(relation_name, set())
        if column is not None:
            actual[relation_name].add(str(column))
        if str(relation_owner) != owner:
            raise ValueError("config relation must be owned by the current database role")
    expected = _config_table_column_map(schema)
    expected_for_existing = (
        expected if require_complete else {name: expected[name] for name in actual}
    )
    if actual != expected_for_existing:
        raise ValueError("config relation columns do not match the expected shape")


def _validate_config_routines(
    cursor: _Cursor, schema: str, owner: str, expected_names: set[str]
) -> None:
    cursor.execute(
        "SELECT p.proname, p.prokind, p.pronargs, "
        "pg_catalog.format_type(p.prorettype, NULL), "
        "pg_catalog.pg_get_userbyid(p.proowner), p.prosecdef "
        "FROM pg_catalog.pg_proc p "
        "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = %s",
        (schema,),
    )
    for (
        name,
        routine_kind,
        argument_count,
        return_type,
        routine_owner,
        security_definer,
    ) in cursor.fetchall():
        if str(name) not in expected_names:
            raise ValueError("config schema contains an unexpected routine")
        if str(routine_kind) != "f" or int(argument_count) != 0 or str(return_type) != "trigger":
            raise ValueError("config schema contains an incompatible routine")
        if str(routine_owner) != owner:
            raise ValueError("config routine must be owned by the current database role")
        if bool(security_definer):
            raise ValueError("config routines must not be SECURITY DEFINER")


def _execute_grant(cursor: _Cursor, statement: sql.Composable) -> None:
    cursor.execute(statement)


def _configure_runtime_grants(
    cursor: _Cursor, schema: str, runtime_role: str, *, version_table: str
) -> None:
    schema_id = sql.Identifier(schema)
    role_id = sql.Identifier(runtime_role)
    grantees = sql.SQL("PUBLIC, {}").format(role_id)
    _execute_grant(
        cursor,
        sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA {} FROM {}").format(schema_id, grantees),
    )
    _execute_grant(
        cursor,
        sql.SQL("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {} FROM {}").format(
            schema_id, grantees
        ),
    )
    _execute_grant(
        cursor,
        sql.SQL("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {} FROM {}").format(
            schema_id, grantees
        ),
    )
    _execute_grant(
        cursor,
        sql.SQL("REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA {} FROM {}").format(
            schema_id, grantees
        ),
    )
    for table_name, columns in (
        *_CONFIG_TABLE_COLUMNS,
        (version_table, _VERSION_TABLE_COLUMNS),
    ):
        column_list = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
        _execute_grant(
            cursor,
            sql.SQL("REVOKE ALL PRIVILEGES ({}) ON TABLE {}.{} FROM {}").format(
                column_list, schema_id, sql.Identifier(table_name), grantees
            ),
        )

    _execute_grant(
        cursor,
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema_id, role_id),
    )
    for table_name in (
        "managed_rules_heads",
        "managed_rules_events",
        "change_orders_heads",
        "change_orders_events",
        "distributions_heads",
        "distributions_events",
        "console_auth_users",
        "console_auth_sessions",
        "as_instances",
    ):
        _execute_grant(
            cursor,
            sql.SQL("GRANT SELECT, INSERT ON TABLE {}.{} TO {}").format(
                schema_id, sql.Identifier(table_name), role_id
            ),
        )
    _execute_grant(
        cursor,
        sql.SQL("GRANT UPDATE, DELETE ON TABLE {}.{} TO {}").format(
            schema_id, sql.Identifier("as_instances"), role_id
        ),
    )
    _execute_grant(
        cursor,
        sql.SQL("GRANT SELECT, INSERT ON TABLE {}.{} TO {}").format(
            schema_id, sql.Identifier(version_table), role_id
        ),
    )

    for table_name, column in (
        ("managed_rules_heads", "current_revision"),
        ("change_orders_heads", "latest_revision"),
        ("distributions_heads", "latest_revision"),
    ):
        _execute_grant(
            cursor,
            sql.SQL("GRANT UPDATE ({}) ON TABLE {}.{} TO {}").format(
                sql.Identifier(column), schema_id, sql.Identifier(table_name), role_id
            ),
        )
    _execute_grant(
        cursor,
        sql.SQL(
            "GRANT UPDATE (roles_json, password_verifier, enabled, updated_at) "
            "ON TABLE {}.console_auth_users TO {}"
        ).format(schema_id, role_id),
    )
    _execute_grant(
        cursor,
        sql.SQL("GRANT UPDATE (revoked_at) ON TABLE {}.console_auth_sessions TO {}").format(
            schema_id, role_id
        ),
    )
    _execute_grant(
        cursor,
        sql.SQL("GRANT SELECT ON TABLE {}.console_auth_bootstrap TO {}").format(schema_id, role_id),
    )


def migrate_database(
    config: MigrationConfig,
    *,
    connect: Callable[[str], _Connection] | None = None,
) -> None:
    """Provision schemas as their owner and grant only the runtime contract."""
    _validate_settings(
        config.owner_dsn,
        config.runtime_role,
        config.config_schema,
        config.audit_schema,
    )
    connector = cast(Callable[[str], _Connection], psycopg.connect) if connect is None else connect
    connection: _Connection | None = None
    try:
        connection = connector(config.owner_dsn)
        owner = _create_config_schema(connection, config.config_schema)
        store_connection = _OwnerMigrationConnection(connection)

        managed_rule_store = PostgresManagedRuleStore(store_connection, schema=config.config_schema)
        change_order_store = PostgresChangeOrderStore(store_connection, schema=config.config_schema)
        distribution_store = PostgresDistributionStore(
            store_connection, schema=config.config_schema
        )
        auth_store = PostgresConsoleAuthStore(store_connection, schema=config.config_schema)
        as_instance_store = PostgresAsInstanceStore(store_connection, schema=config.config_schema)
        version_table = _version_table_name(config.config_schema)
        version_store = PostgresVersionStore(store_connection, table=version_table)
        audit_store = PostgresAuditStore(store_connection, schema=config.audit_schema)

        config_stores = (
            managed_rule_store,
            change_order_store,
            distribution_store,
        )
        expected_routines = _expected_routine_names(config_stores)
        cursor = connection.cursor()
        try:
            _validate_config_relations(cursor, config.config_schema, owner, require_complete=False)
            _validate_config_columns(cursor, config.config_schema, owner, require_complete=False)
            _validate_config_routines(cursor, config.config_schema, owner, expected_routines)
            schema_id = sql.Identifier(config.config_schema)
            for object_kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
                cursor.execute(
                    sql.SQL(
                        "ALTER DEFAULT PRIVILEGES IN SCHEMA {} REVOKE ALL ON {} FROM PUBLIC"
                    ).format(schema_id, sql.SQL(object_kind))
                )
        finally:
            cursor.close()

        managed_rule_store.ensure_schema()
        change_order_store.ensure_schema()
        distribution_store.ensure_schema()
        auth_store.ensure_schema()
        as_instance_store.ensure_schema()
        search_path_cursor = connection.cursor()
        try:
            search_path_cursor.execute(
                sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(
                    sql.Identifier(config.config_schema)
                )
            )
        finally:
            search_path_cursor.close()
        version_store.ensure_schema()
        audit_store.ensure_schema(config.runtime_role)

        cursor = connection.cursor()
        try:
            _validate_config_relations(cursor, config.config_schema, owner, require_complete=True)
            _validate_config_columns(cursor, config.config_schema, owner, require_complete=True)
            _validate_config_routines(cursor, config.config_schema, owner, expected_routines)
            _configure_runtime_grants(
                cursor,
                config.config_schema,
                config.runtime_role,
                version_table=version_table,
            )
        finally:
            cursor.close()
        connection.commit()
    except BaseException:
        if connection is not None:
            with suppress(BaseException):
                connection.rollback()
        raise
    finally:
        if connection is not None:
            with suppress(BaseException):
                connection.close()


def main() -> int:
    """Run the owner-only migration command with secret-free diagnostics."""
    try:
        config = load_migration_config()
    except ValueError:
        print("Config database migration configuration is invalid.", file=sys.stderr)
        return 1
    try:
        migrate_database(config)
    except Exception:
        print("Config database migration failed.", file=sys.stderr)
        return 1
    print("Config database migration completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
