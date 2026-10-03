"""PostgreSQL integration coverage for owner-only runtime-role provisioning."""

from __future__ import annotations

import os
import sys
import uuid
import warnings
from contextlib import suppress
from typing import Any

import pytest

pytestmark = pytest.mark.integration

TEST_DSN = os.environ.get(
    "AS_PG_TEST_DSN", "postgresql://postgres:secret@127.0.0.1:55432/as_config"
)
_CONNECT_TIMEOUT_SECONDS = 3
_NETWORK_UNAVAILABLE_MESSAGES = (
    "connection refused",
    "connection timed out",
    "timeout expired",
    "operation timed out",
    "no route to host",
    "network is unreachable",
)


def _is_network_unavailable(exc: BaseException, operational_error: type[BaseException]) -> bool:
    if not isinstance(exc, operational_error):
        return False
    normalized = str(exc).lower()
    return any(marker in normalized for marker in _NETWORK_UNAVAILABLE_MESSAGES)


def _table_counts(
    cursor: Any, sql: Any, schema: str, table_names: tuple[str, ...]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in table_names:
        cursor.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(schema), sql.Identifier(table_name)
            )
        )
        row = cursor.fetchone()
        assert row is not None
        counts[table_name] = int(row[0])
    return counts


def test_owner_migration_creates_isolated_least_privilege_runtime_role() -> None:
    driver = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    from as_config_service.audit_store import PostgresAuditStore
    from as_config_service.auth import PostgresConsoleAuthStore
    from as_config_service.change_order_store import PostgresChangeOrderStore
    from as_config_service.distribution_store import PostgresDistributionStore
    from as_config_service.managed_rule_store import PostgresManagedRuleStore
    from as_config_service.migrate import MigrationConfig, migrate_database
    from as_config_service.postgres_store import PostgresVersionStore
    from as_platform.api.contract import ConfigBundle

    suffix = uuid.uuid4().hex[:12]
    config_schema = f"migrate_config_test_{suffix}"
    audit_schema = f"migrate_audit_test_{suffix}"
    runtime_role = f"migrate_runtime_{suffix}"
    login_role = f"migrate_login_{suffix}"
    password = uuid.uuid4().hex
    owner_connection = None
    runtime_connection = None
    runtime_role_created = False
    login_role_created = False
    migration_started = False

    try:
        try:
            owner_connection = driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
        except Exception as exc:
            if _is_network_unavailable(exc, driver.OperationalError):
                pytest.skip("PostgreSQL is unavailable")
            raise

        cursor = owner_connection.cursor()
        cursor.execute("SHOW server_version_num")
        server_version_num = int(cursor.fetchone()[0])
        assert server_version_num >= 120000, (
            f"PostgreSQL server_version_num={server_version_num}; "
            "PostgreSQL 12 or newer is required"
        )
        cursor.execute("SELECT current_user")
        owner_role = str(cursor.fetchone()[0])
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace "
            "WHERE nspname = ANY(%s)), "
            "EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = ANY(%s))",
            ([config_schema, audit_schema], [runtime_role, login_role]),
        )
        schema_collision, role_collision = cursor.fetchone()
        assert not schema_collision
        assert not role_collision

        cursor.execute(
            sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEROLE").format(
                sql.Identifier(runtime_role)
            )
        )
        runtime_role_created = True
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEROLE PASSWORD {}").format(
                sql.Identifier(login_role), sql.Literal(password)
            )
        )
        login_role_created = True
        cursor.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(runtime_role), sql.Identifier(login_role)
            )
        )
        owner_connection.commit()
        cursor.close()

        config = MigrationConfig(
            owner_dsn=TEST_DSN,
            runtime_role=runtime_role,
            config_schema=config_schema,
            audit_schema=audit_schema,
        )

        def connect_owner(dsn: str) -> Any:
            try:
                return driver.connect(dsn, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
            except Exception as exc:
                if _is_network_unavailable(exc, driver.OperationalError):
                    pytest.skip("PostgreSQL is unavailable")
                raise

        migration_started = True
        migrate_database(config, connect=connect_owner)

        login_dsn = make_conninfo(TEST_DSN, user=login_role, password=password)
        try:
            runtime_connection = driver.connect(login_dsn, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
        except Exception as exc:
            if _is_network_unavailable(exc, driver.OperationalError):
                pytest.skip("PostgreSQL is unavailable")
            raise
        runtime_cursor = runtime_connection.cursor()
        runtime_cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(runtime_role)))
        runtime_connection.commit()
        runtime_cursor.execute("SELECT current_user, session_user")
        assert runtime_cursor.fetchone() == (runtime_role, login_role)
        runtime_connection.commit()

        owner_cursor = owner_connection.cursor()
        owner_cursor.execute(
            "SELECT n.nspname, pg_catalog.pg_get_userbyid(n.nspowner) "
            "FROM pg_catalog.pg_namespace n WHERE n.nspname = ANY(%s)",
            ([config_schema, audit_schema],),
        )
        assert dict(owner_cursor.fetchall()) == {
            config_schema: owner_role,
            audit_schema: owner_role,
        }

        owner_cursor.execute(
            "SELECT rolname, rolsuper, rolcreaterole, rolcanlogin "
            "FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)",
            ([runtime_role, login_role],),
        )
        role_properties = {
            str(row[0]): tuple(bool(value) for value in row[1:]) for row in owner_cursor
        }
        assert role_properties == {
            runtime_role: (False, False, False),
            login_role: (False, False, True),
        }
        owner_cursor.execute(
            "SELECT count(*) FROM pg_catalog.pg_auth_members m "
            "JOIN pg_catalog.pg_roles member ON member.oid = m.member "
            "WHERE member.rolname = %s",
            (runtime_role,),
        )
        assert owner_cursor.fetchone()[0] == 0
        owner_cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members m "
            "JOIN pg_catalog.pg_roles granted ON granted.oid = m.roleid "
            "JOIN pg_catalog.pg_roles member ON member.oid = m.member "
            "WHERE granted.rolname = %s AND member.rolname = %s)",
            (runtime_role, login_role),
        )
        assert owner_cursor.fetchone()[0] is True

        owner_cursor.execute(
            "SELECT n.nspname, "
            "pg_catalog.has_schema_privilege(%s, n.oid, 'USAGE'), "
            "pg_catalog.has_schema_privilege(%s, n.oid, 'CREATE') "
            "FROM pg_catalog.pg_namespace n WHERE n.nspname = ANY(%s)",
            (runtime_role, runtime_role, [config_schema, audit_schema]),
        )
        schema_privileges = {
            str(name): (bool(can_use), bool(can_create))
            for name, can_use, can_create in owner_cursor.fetchall()
        }
        assert schema_privileges == {
            config_schema: (True, False),
            audit_schema: (True, False),
        }

        version_table = f"{config_schema}_config_versions"
        expected_updates = {
            "managed_rules_heads": {"current_revision"},
            "managed_rules_events": set(),
            "change_orders_heads": {"latest_revision"},
            "change_orders_events": set(),
            "distributions_heads": {"latest_revision"},
            "distributions_events": set(),
            "console_auth_users": {"roles_json", "password_verifier", "enabled", "updated_at"},
            "console_auth_sessions": {"revoked_at"},
            "console_auth_bootstrap": set(),
            version_table: set(),
        }
        for table_name, update_columns in expected_updates.items():
            owner_cursor.execute(
                "SELECT pg_catalog.has_table_privilege(%s, c.oid, 'SELECT'), "
                "pg_catalog.has_table_privilege(%s, c.oid, 'INSERT'), "
                "pg_catalog.has_table_privilege(%s, c.oid, 'UPDATE'), "
                "pg_catalog.has_table_privilege(%s, c.oid, 'DELETE'), "
                "pg_catalog.has_table_privilege(%s, c.oid, 'TRUNCATE') "
                "FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s",
                (runtime_role,) * 5 + (config_schema, table_name),
            )
            table_privileges = owner_cursor.fetchone()
            assert table_privileges is not None
            can_select, can_insert, can_update, can_delete, can_truncate = map(
                bool, table_privileges
            )
            assert can_select is True
            assert can_insert is (table_name != "console_auth_bootstrap")
            assert can_update is False
            assert can_delete is False
            assert can_truncate is False

            owner_cursor.execute(
                "SELECT a.attname, pg_catalog.has_column_privilege(%s, c.oid, a.attname, 'UPDATE') "
                "FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid "
                "WHERE n.nspname = %s AND c.relname = %s "
                "AND a.attnum > 0 AND NOT a.attisdropped",
                (runtime_role, config_schema, table_name),
            )
            column_privileges = {
                str(column): bool(can_update_column)
                for column, can_update_column in owner_cursor.fetchall()
            }
            assert {column for column, allowed in column_privileges.items() if allowed} == (
                update_columns
            )

        owner_cursor.execute(
            "SELECT c.relname, a.privilege_type "
            "FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE("
            "c.relacl, pg_catalog.acldefault('r', c.relowner))) a "
            "WHERE n.nspname = %s AND c.relkind = 'r' AND a.grantee = 0",
            (config_schema,),
        )
        assert owner_cursor.fetchall() == []
        owner_cursor.execute(
            "SELECT p.proname, a.privilege_type "
            "FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
            "CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE("
            "p.proacl, pg_catalog.acldefault('f', p.proowner))) a "
            "WHERE n.nspname = %s AND a.grantee = 0",
            (config_schema,),
        )
        assert owner_cursor.fetchall() == []
        owner_cursor.execute(
            "SELECT p.proname, pg_catalog.has_function_privilege(%s, p.oid, 'EXECUTE') "
            "FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = %s",
            (runtime_role, config_schema),
        )
        config_functions = owner_cursor.fetchall()
        assert config_functions
        assert all(bool(can_execute) is False for _name, can_execute in config_functions)
        owner_connection.commit()
        owner_cursor.close()

        audit_store = PostgresAuditStore(
            runtime_connection, prefix="console_audit", schema=audit_schema
        )
        audit_store.validate_runtime_connection()

        managed_rule_store = PostgresManagedRuleStore(runtime_connection, schema=config_schema)
        change_order_store = PostgresChangeOrderStore(runtime_connection, schema=config_schema)
        distribution_store = PostgresDistributionStore(runtime_connection, schema=config_schema)
        auth_store = PostgresConsoleAuthStore(runtime_connection, schema=config_schema)

        config_tables = tuple(expected_updates)
        owner_cursor = owner_connection.cursor()
        counts_before = _table_counts(owner_cursor, sql, config_schema, config_tables)
        owner_connection.commit()

        assert managed_rule_store.list_latest() == ()
        assert managed_rule_store.get("missing-rule") is None
        assert change_order_store.list_latest() == ()
        assert change_order_store.get("missing-order") is None
        assert distribution_store.list_latest() == ()
        assert distribution_store.get("missing-distribution") is None
        assert auth_store.list_users() == ()
        assert auth_store.get_user("missing-user") is None
        runtime_connection.rollback()

        counts_after = _table_counts(owner_cursor, sql, config_schema, config_tables)
        owner_connection.commit()
        assert counts_after == counts_before
        owner_cursor.close()

        runtime_cursor.execute(
            sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(config_schema))
        )
        version_store = PostgresVersionStore(runtime_connection, table=version_table)
        appended = version_store.append(
            ConfigBundle(version="1", rules=(), toggles=()),
            now=1.0,
            change_id="migrate-integration-test",
        )
        assert appended.version == 1
        runtime_connection.commit()

    finally:
        primary_exception = sys.exc_info()[1]
        cleanup_errors: list[BaseException] = []
        if runtime_connection is not None:
            with suppress(BaseException):
                runtime_connection.rollback()
            try:
                runtime_connection.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
        if owner_connection is not None:
            try:
                owner_connection.rollback()
                cleanup_cursor = owner_connection.cursor()
                if runtime_role_created and login_role_created:
                    cleanup_cursor.execute(
                        sql.SQL("REVOKE {} FROM {}").format(
                            sql.Identifier(runtime_role), sql.Identifier(login_role)
                        )
                    )
                if migration_started:
                    cleanup_cursor.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                            sql.Identifier(config_schema)
                        )
                    )
                    cleanup_cursor.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                            sql.Identifier(audit_schema)
                        )
                    )
                if login_role_created:
                    cleanup_cursor.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(login_role))
                    )
                if runtime_role_created:
                    cleanup_cursor.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(runtime_role))
                    )
                owner_connection.commit()
                cleanup_cursor.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
                with suppress(BaseException):
                    owner_connection.rollback()
            try:
                owner_connection.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            error_types = ", ".join(type(exc).__name__ for exc in cleanup_errors)
            message = f"PostgreSQL migration test cleanup failed: {error_types}"
            if primary_exception is not None:
                with suppress(BaseException):
                    warnings.warn(message, RuntimeWarning, stacklevel=2)
            else:
                raise RuntimeError(message) from None
