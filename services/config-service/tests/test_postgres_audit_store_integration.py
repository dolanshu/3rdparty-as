"""PostgreSQL-backed audit durability and immutability tests. ADR-0024, REQ-S-4."""

from __future__ import annotations

import hashlib
import os
import sys
import uuid
import warnings
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import pytest

from as_config_service.audit_store import PostgresAuditStore
from as_console.access import AuditOutcome, AuditRecord

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


@dataclass(frozen=True)
class PgHarness:
    store: PostgresAuditStore
    owner_store: PostgresAuditStore
    owner_connection: Any
    runtime_connection: Any
    driver: Any
    schema: str
    runtime_role: str


def _is_network_unavailable(exc: BaseException, operational_error: type[BaseException]) -> bool:
    if not isinstance(exc, operational_error):
        return False
    normalized = str(exc).lower()
    return any(marker in normalized for marker in _NETWORK_UNAVAILABLE_MESSAGES)


def _record(action: str = "rule.update", **overrides: object) -> AuditRecord:
    values: dict[str, object] = {
        "actor": "ops-alice",
        "action": action,
        "resource": "rule:international",
        "outcome": AuditOutcome.ALLOWED,
        "at": 1_700_000_000.25,
    }
    values.update(overrides)
    return AuditRecord(**values)  # type: ignore[arg-type]


def _relation(schema: str, table: str) -> Any:
    from psycopg import sql

    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))


@pytest.fixture()
def pg() -> Iterator[PgHarness]:
    driver = pytest.importorskip("psycopg")
    from psycopg import sql

    parsed = urlparse(TEST_DSN)
    owner_connection = None
    runtime_connection = None
    schema = f"audit_test_{uuid.uuid4().hex[:12]}"
    runtime_role = f"audit_runtime_{uuid.uuid4().hex[:12]}"
    role_created = False
    try:
        try:
            owner_connection = driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
        except Exception as exc:
            if _is_network_unavailable(exc, driver.OperationalError):
                pytest.skip(
                    f"no PostgreSQL server reachable at {parsed.hostname}:{parsed.port}: {exc}"
                )
            raise

        cursor = owner_connection.cursor()
        cursor.execute("SHOW server_version_num")
        server_version_num = int(cursor.fetchone()[0])
        assert server_version_num >= 120000, (
            f"PostgreSQL server_version_num={server_version_num}; "
            "PostgreSQL 12 or newer is required"
        )
        cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(runtime_role)))
        role_created = True
        owner_connection.commit()

        owner_store = PostgresAuditStore(owner_connection, prefix="console_audit", schema=schema)
        owner_store.ensure_schema(runtime_role=runtime_role)

        runtime_connection = driver.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
        runtime_connection.cursor().execute(
            sql.SQL("SET ROLE {}").format(sql.Identifier(runtime_role))
        )
        runtime_connection.commit()
        store = PostgresAuditStore(runtime_connection, prefix="console_audit", schema=schema)
        yield PgHarness(
            store=store,
            owner_store=owner_store,
            owner_connection=owner_connection,
            runtime_connection=runtime_connection,
            driver=driver,
            schema=schema,
            runtime_role=runtime_role,
        )
    finally:
        primary_exception = sys.exc_info()[1]
        cleanup_errors: list[BaseException] = []
        if runtime_connection is not None:
            try:
                runtime_connection.rollback()
                runtime_connection.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
        if owner_connection is not None:
            try:
                owner_connection.rollback()
                cursor = owner_connection.cursor()
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
                )
                if role_created:
                    cursor.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(runtime_role))
                    )
                owner_connection.commit()
                cursor.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
                with suppress(BaseException):
                    owner_connection.rollback()
            try:
                owner_connection.close()
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


def test_runtime_role_can_append_and_read_only_with_effective_grants(pg: PgHarness) -> None:
    from psycopg import sql

    table = _relation(pg.schema, pg.store.table)
    cursor = pg.owner_connection.cursor()
    cursor.execute(
        "SELECT r.rolsuper, pg_catalog.pg_get_userbyid(c.relowner), "
        "pg_catalog.has_table_privilege(%s, c.oid, 'SELECT'), "
        "pg_catalog.has_table_privilege(%s, c.oid, 'INSERT'), "
        "pg_catalog.has_table_privilege(%s, c.oid, 'UPDATE'), "
        "pg_catalog.has_table_privilege(%s, c.oid, 'DELETE'), "
        "pg_catalog.has_table_privilege(%s, c.oid, 'TRUNCATE'), "
        "pg_catalog.has_sequence_privilege(%s, %s, 'USAGE'), "
        "pg_catalog.has_sequence_privilege(%s, %s, 'SELECT'), "
        "pg_catalog.has_sequence_privilege(%s, %s, 'UPDATE') "
        "FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE r.rolname = %s AND n.nspname = %s AND c.relname = %s",
        (
            pg.runtime_role,
            pg.runtime_role,
            pg.runtime_role,
            pg.runtime_role,
            pg.runtime_role,
            pg.runtime_role,
            f"{pg.schema}.{pg.store.sequence}",
            pg.runtime_role,
            f"{pg.schema}.{pg.store.sequence}",
            pg.runtime_role,
            f"{pg.schema}.{pg.store.sequence}",
            pg.runtime_role,
            pg.schema,
            pg.store.table,
        ),
    )
    (
        is_superuser,
        table_owner,
        can_select,
        can_insert,
        can_update,
        can_delete,
        can_truncate,
        can_use_sequence,
        can_select_sequence,
        can_update_sequence,
    ) = cursor.fetchone()
    assert is_superuser is False
    assert table_owner != pg.runtime_role
    assert (can_select, can_insert) == (True, True)
    assert (can_update, can_delete, can_truncate) == (False, False, False)
    assert (can_use_sequence, can_select_sequence, can_update_sequence) == (True, True, False)

    cursor.execute(
        "SELECT pg_catalog.pg_get_userbyid(n.nspowner), "
        "pg_catalog.pg_get_userbyid(s.relowner), "
        "pg_catalog.has_schema_privilege(%s, n.oid, 'USAGE'), "
        "pg_catalog.has_schema_privilege(%s, n.oid, 'CREATE') "
        "FROM pg_catalog.pg_namespace n "
        "JOIN pg_catalog.pg_class s ON s.relnamespace = n.oid "
        "WHERE n.nspname = %s AND s.relname = %s",
        (pg.runtime_role, pg.runtime_role, pg.schema, pg.store.sequence),
    )
    schema_owner, sequence_owner, can_use_schema, can_create_in_schema = cursor.fetchone()
    assert schema_owner != pg.runtime_role
    assert sequence_owner != pg.runtime_role
    assert can_use_schema is True
    assert can_create_in_schema is False

    cursor.execute(
        "SELECT c.relkind, a.grantee, a.privilege_type "
        "FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "CROSS JOIN LATERAL pg_catalog.aclexplode("
        "COALESCE(c.relacl, pg_catalog.acldefault(c.relkind, c.relowner))) a "
        "WHERE n.nspname = %s AND c.relname IN (%s, %s) AND a.grantee = 0",
        (pg.schema, pg.store.table, pg.store.sequence),
    )
    assert cursor.fetchall() == []

    first = pg.store.append(
        _record(
            before_value={"enabled": False, "name": "old"},
            after_value={"enabled": True, "name": "new"},
            detail="must not be stored",
        )
    )
    second = pg.store.append(_record("rule.read", outcome=AuditOutcome.DENIED))
    pg.runtime_connection.commit()
    history = pg.store.list_events()
    pg.runtime_connection.commit()

    assert first.sequence_id < second.sequence_id
    assert [event.sequence_id for event in history] == [first.sequence_id, second.sequence_id]
    assert history[0].record.before_value == {"enabled": False, "name": "old"}
    assert history[0].record.after_value == {"enabled": True, "name": "new"}
    assert history[1].record.outcome is AuditOutcome.DENIED

    cursor.execute(
        sql.SQL(
            "SELECT actor, action, resource, outcome, occurred_at, before_json, after_json "
            "FROM {} ORDER BY id"
        ).format(table)
    )
    stored_rows = cursor.fetchall()
    assert stored_rows == [
        (
            "ops-alice",
            "rule.update",
            "rule:international",
            "allowed",
            1_700_000_000.25,
            '{"enabled":false,"name":"old"}',
            '{"enabled":true,"name":"new"}',
        ),
        (
            "ops-alice",
            "rule.read",
            "rule:international",
            "denied",
            1_700_000_000.25,
            None,
            None,
        ),
    ]

    for statement in (
        sql.SQL("UPDATE {} SET actor = 'forged'").format(table),
        sql.SQL("DELETE FROM {}").format(table),
        sql.SQL("TRUNCATE TABLE {}").format(table),
    ):
        with pytest.raises(pg.driver.errors.InsufficientPrivilege):
            pg.runtime_connection.cursor().execute(statement)
        pg.runtime_connection.rollback()

    with pytest.raises(pg.driver.errors.InsufficientPrivilege):
        pg.runtime_connection.cursor().execute(
            sql.SQL("CREATE TABLE {}.runtime_forbidden (id integer)").format(
                sql.Identifier(pg.schema)
            )
        )
    pg.runtime_connection.rollback()

    for statement in (
        sql.SQL("UPDATE {} SET actor = 'forged'").format(table),
        sql.SQL("DELETE FROM {}").format(table),
        sql.SQL("TRUNCATE TABLE {}").format(table),
    ):
        with pytest.raises(pg.driver.errors.CheckViolation):
            pg.owner_connection.cursor().execute(statement)
        pg.owner_connection.rollback()


def test_commit_false_rolls_back_and_failed_append_rolls_back_staged_events(
    pg: PgHarness,
) -> None:
    from psycopg import sql

    table = _relation(pg.schema, pg.store.table)
    pg.store.append(_record("baseline"))
    pg.runtime_connection.commit()

    pg.store.append(_record("caller-rollback"), commit=False)
    pg.runtime_connection.rollback()
    assert [event.record.action for event in pg.store.list_events()] == ["baseline"]
    pg.runtime_connection.commit()

    cursor = pg.owner_connection.cursor()
    cursor.execute(
        sql.SQL(
            "ALTER TABLE {} ADD CONSTRAINT audit_test_failure CHECK (action <> 'force-failure')"
        ).format(table)
    )
    pg.owner_connection.commit()

    pg.store.append(_record("staged-before-failure"), commit=False)
    with pytest.raises(pg.driver.errors.CheckViolation):
        pg.store.append(_record("force-failure"), commit=False)

    cursor = pg.owner_connection.cursor()
    cursor.execute(sql.SQL("SELECT action FROM {} ORDER BY id").format(table))
    assert cursor.fetchall() == [("baseline",)]
    pg.owner_connection.rollback()
    assert [event.record.action for event in pg.store.list_events()] == ["baseline"]
    pg.runtime_connection.commit()


def test_schema_setup_rejects_membership_with_effective_mutation_privileges(
    pg: PgHarness,
) -> None:
    from psycopg import sql

    helper_role = f"audit_power_{uuid.uuid4().hex[:12]}"
    cursor = pg.owner_connection.cursor()
    table = _relation(pg.schema, pg.store.table)
    cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(helper_role)))
    cursor.execute(
        sql.SQL("GRANT UPDATE ON TABLE {} TO {}").format(table, sql.Identifier(helper_role))
    )
    cursor.execute(
        sql.SQL("GRANT {} TO {}").format(
            sql.Identifier(helper_role), sql.Identifier(pg.runtime_role)
        )
    )
    pg.owner_connection.commit()

    try:
        cursor.execute(
            "SELECT pg_catalog.has_table_privilege(%s, %s, 'UPDATE')",
            (pg.runtime_role, f"{pg.schema}.{pg.store.table}"),
        )
        assert cursor.fetchone()[0] is True
        with pytest.raises(ValueError, match="member of another database role"):
            pg.owner_store.ensure_schema(runtime_role=pg.runtime_role)
    finally:
        pg.owner_connection.rollback()
        cursor = pg.owner_connection.cursor()
        cursor.execute(
            sql.SQL("REVOKE {} FROM {}").format(
                sql.Identifier(helper_role), sql.Identifier(pg.runtime_role)
            )
        )
        cursor.execute(
            sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(table, sql.Identifier(helper_role))
        )
        cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(helper_role)))
        pg.owner_connection.commit()


def test_schema_setup_rejects_createrole_before_creating_schema(pg: PgHarness) -> None:
    from psycopg import sql

    privileged_role = f"audit_createrole_{uuid.uuid4().hex[:12]}"
    schema = f"audit_createrole_schema_{uuid.uuid4().hex[:8]}"
    store = PostgresAuditStore(pg.owner_connection, schema=schema)
    cursor = pg.owner_connection.cursor()
    cursor.execute(
        sql.SQL("CREATE ROLE {} NOLOGIN CREATEROLE").format(sql.Identifier(privileged_role))
    )
    pg.owner_connection.commit()

    try:
        with pytest.raises(ValueError, match="must not have CREATEROLE"):
            store.ensure_schema(runtime_role=privileged_role)

        cursor = pg.owner_connection.cursor()
        cursor.execute("SELECT pg_catalog.to_regnamespace(%s)", (schema,))
        assert cursor.fetchone()[0] is None
    finally:
        pg.owner_connection.rollback()
        cursor = pg.owner_connection.cursor()
        cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(privileged_role)))
        pg.owner_connection.commit()


def test_schema_setup_rejects_unexpected_trigger_without_granting_insert(pg: PgHarness) -> None:
    from psycopg import sql

    table = _relation(pg.schema, pg.store.table)
    rewrite_function = sql.SQL("{}.{}").format(
        sql.Identifier(pg.schema), sql.Identifier("rewrite_audit_insert")
    )
    cursor = pg.owner_connection.cursor()
    cursor.execute(
        sql.SQL("REVOKE ALL PRIVILEGES ON TABLE {} FROM {}").format(
            table, sql.Identifier(pg.runtime_role)
        )
    )
    cursor.execute(
        sql.SQL(
            "CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $rewrite$ "
            "BEGIN NEW.actor := 'rewritten'; RETURN NEW; END; $rewrite$"
        ).format(rewrite_function)
    )
    cursor.execute(
        sql.SQL(
            "CREATE TRIGGER audit_rewrite_before_insert BEFORE INSERT ON {} "
            "FOR EACH ROW EXECUTE FUNCTION {}()"
        ).format(table, rewrite_function)
    )
    pg.owner_connection.commit()

    with pytest.raises(RuntimeError, match="unexpected or incompatible function"):
        pg.owner_store.ensure_schema(runtime_role=pg.runtime_role)

    cursor = pg.owner_connection.cursor()
    cursor.execute(
        "SELECT pg_catalog.has_table_privilege(%s, %s, 'INSERT')",
        (pg.runtime_role, f"{pg.schema}.{pg.store.table}"),
    )
    assert cursor.fetchone()[0] is False


def test_schema_setup_allows_only_its_objects_and_is_idempotent(pg: PgHarness) -> None:
    from psycopg import sql

    schema = f"AuditAllow{uuid.uuid4().hex[:8]}"
    prefix = f"ConsoleAudit{uuid.uuid4().hex[:8]}"
    store = PostgresAuditStore(pg.owner_connection, prefix=prefix, schema=schema)

    try:
        store.ensure_schema(runtime_role=pg.runtime_role)
        store.ensure_schema(runtime_role=pg.runtime_role)

        cursor = pg.owner_connection.cursor()
        cursor.execute(
            "SELECT c.relname, c.relkind FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s ORDER BY c.relname",
            (schema,),
        )
        assert cursor.fetchall() == sorted(
            [
                (store.table, "r"),
                (store.sequence, "S"),
                ("audit_event_id_pkey", "i"),
            ]
        )

        cursor.execute(
            "SELECT t.typname, t.typtype FROM pg_catalog.pg_type t "
            "JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = %s ORDER BY t.typname",
            (schema,),
        )
        assert cursor.fetchall() == sorted(
            [(store.table, "c"), (store.sequence, "c"), (f"_{store.table}", "b")]
        )

        cursor.execute(
            "SELECT p.proname, p.prosecdef FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = %s ORDER BY p.proname",
            (schema,),
        )
        digest = hashlib.sha256(f"{schema}.{prefix}".encode("ascii")).hexdigest()[:16]
        assert cursor.fetchall() == sorted(
            [
                (f"as_audit_row_guard_{digest}", False),
                (f"as_audit_truncate_guard_{digest}", False),
            ]
        )
    finally:
        pg.owner_connection.rollback()
        cursor = pg.owner_connection.cursor()
        cursor.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        pg.owner_connection.commit()


def test_schema_setup_rejects_public_security_definer_function_before_grants(
    pg: PgHarness,
) -> None:
    from psycopg import sql

    schema = f"AuditUnsafe{uuid.uuid4().hex[:8]}"
    prefix = f"ConsoleAudit{uuid.uuid4().hex[:8]}"
    store = PostgresAuditStore(pg.owner_connection, prefix=prefix, schema=schema)
    rogue_function = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier("public_exec"))
    cursor = pg.owner_connection.cursor()
    cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    cursor.execute(
        sql.SQL(
            "CREATE FUNCTION {}() RETURNS integer LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'"
        ).format(rogue_function)
    )
    pg.owner_connection.commit()

    try:
        cursor = pg.owner_connection.cursor()
        cursor.execute(
            "SELECT EXISTS ("
            "SELECT 1 FROM pg_catalog.pg_proc p "
            "CROSS JOIN LATERAL pg_catalog.aclexplode("
            "COALESCE(p.proacl, pg_catalog.acldefault('f', p.proowner))) acl "
            "WHERE p.oid = pg_catalog.to_regprocedure(%s) "
            "AND acl.grantee = 0 AND acl.privilege_type = 'EXECUTE')",
            (f'"{schema}".public_exec()',),
        )
        assert cursor.fetchone()[0] is True

        with pytest.raises(RuntimeError, match="unexpected or incompatible function"):
            store.ensure_schema(runtime_role=pg.runtime_role)

        cursor = pg.owner_connection.cursor()
        cursor.execute(
            "SELECT pg_catalog.has_schema_privilege(%s, %s, 'USAGE'), pg_catalog.to_regclass(%s)",
            (pg.runtime_role, schema, f'"{schema}"."{store.table}"'),
        )
        assert cursor.fetchone() == (False, None)
    finally:
        pg.owner_connection.rollback()
        cursor = pg.owner_connection.cursor()
        cursor.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        pg.owner_connection.commit()


def test_schema_setup_rejects_extra_check_constraint_before_grants(pg: PgHarness) -> None:
    from psycopg import sql

    from as_config_service.audit_store import _AUDIT_CONSTRAINTS

    schema = f"audit_extra_check_{uuid.uuid4().hex[:12]}"
    prefix = f"audit_events_{uuid.uuid4().hex[:8]}"
    function_name = f"audit_check_target_{uuid.uuid4().hex[:12]}"
    store = PostgresAuditStore(pg.owner_connection, prefix=prefix, schema=schema)
    table = _relation(schema, store.table)
    sequence = _relation(schema, store.sequence)
    function = sql.SQL("{}.{}").format(sql.Identifier("public"), sql.Identifier(function_name))

    try:
        cursor = pg.owner_connection.cursor()
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        cursor.execute(
            sql.SQL(
                "CREATE FUNCTION {}(text) RETURNS boolean LANGUAGE sql SECURITY DEFINER "
                "AS 'SELECT true'"
            ).format(function)
        )
        cursor.execute(
            sql.SQL(
                "CREATE SEQUENCE {} AS bigint START WITH 1 INCREMENT BY 1 MINVALUE 1 "
                "MAXVALUE 9223372036854775807 NO CYCLE"
            ).format(sequence)
        )
        expected_constraints = sql.SQL(", ").join(
            sql.SQL("CONSTRAINT {} {}").format(sql.Identifier(name), sql.SQL(definition))
            for name, (_, definition) in _AUDIT_CONSTRAINTS.items()
        )
        cursor.execute(
            sql.SQL(
                "CREATE TABLE {} ("
                "id BIGINT NOT NULL DEFAULT nextval({}::regclass), "
                "actor TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL, "
                "outcome TEXT NOT NULL, occurred_at DOUBLE PRECISION NOT NULL, "
                "before_json TEXT, after_json TEXT, {}, "
                "CONSTRAINT audit_event_external_check CHECK ({}.{}(actor)))"
            ).format(
                table,
                sql.Literal(f"{schema}.{store.sequence}"),
                expected_constraints,
                sql.Identifier("public"),
                sql.Identifier(function_name),
            )
        )
        cursor.execute(sql.SQL("ALTER SEQUENCE {} OWNED BY {}.id").format(sequence, table))
        pg.owner_connection.commit()

        with pytest.raises(RuntimeError, match="unexpected constraint"):
            store.ensure_schema(runtime_role=pg.runtime_role)

        cursor = pg.owner_connection.cursor()
        cursor.execute(
            "SELECT pg_catalog.has_schema_privilege(%s, pg_catalog.to_regnamespace(%s), 'USAGE'), "
            "pg_catalog.has_table_privilege(%s, pg_catalog.to_regclass(%s), 'INSERT')",
            (
                pg.runtime_role,
                schema,
                pg.runtime_role,
                f'"{schema}"."{store.table}"',
            ),
        )
        assert cursor.fetchone() == (False, False)
    finally:
        pg.owner_connection.rollback()
        cursor = pg.owner_connection.cursor()
        cursor.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        cursor.execute(sql.SQL("DROP FUNCTION IF EXISTS {}(text)").format(function))
        pg.owner_connection.commit()


def test_schema_setup_rejects_descending_cycling_sequence_before_grants(
    pg: PgHarness,
) -> None:
    from psycopg import sql

    schema = f"AuditSequence{uuid.uuid4().hex[:8]}"
    prefix = f"ConsoleAudit{uuid.uuid4().hex[:8]}"
    store = PostgresAuditStore(pg.owner_connection, prefix=prefix, schema=schema)
    cursor = pg.owner_connection.cursor()
    cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    cursor.execute(
        sql.SQL(
            "CREATE SEQUENCE {}.{} AS bigint START WITH 1 MINVALUE 1 "
            "MAXVALUE 9223372036854775807 INCREMENT BY -1 CYCLE"
        ).format(sql.Identifier(schema), sql.Identifier(store.sequence))
    )
    pg.owner_connection.commit()

    try:
        with pytest.raises(RuntimeError, match="sequence settings are incompatible"):
            store.ensure_schema(runtime_role=pg.runtime_role)

        cursor = pg.owner_connection.cursor()
        cursor.execute(
            "SELECT pg_catalog.has_schema_privilege(%s, pg_catalog.to_regnamespace(%s), 'USAGE'), "
            "pg_catalog.has_sequence_privilege(%s, pg_catalog.to_regclass(%s), 'USAGE'), "
            "pg_catalog.to_regclass(%s)",
            (
                pg.runtime_role,
                f'"{schema}"',
                pg.runtime_role,
                f'"{schema}"."{store.sequence}"',
                f'"{schema}"."{store.table}"',
            ),
        )
        assert cursor.fetchone() == (False, False, None)
    finally:
        pg.owner_connection.rollback()
        cursor = pg.owner_connection.cursor()
        cursor.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        pg.owner_connection.commit()


def test_schema_setup_rejects_membership_with_effective_sequence_update_privilege(
    pg: PgHarness,
) -> None:
    from psycopg import sql

    helper_role = f"audit_seq_power_{uuid.uuid4().hex[:12]}"
    sequence = _relation(pg.schema, pg.store.sequence)
    cursor = pg.owner_connection.cursor()
    cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(helper_role)))
    cursor.execute(
        sql.SQL("GRANT UPDATE ON SEQUENCE {} TO {}").format(sequence, sql.Identifier(helper_role))
    )
    cursor.execute(
        sql.SQL("GRANT {} TO {}").format(
            sql.Identifier(helper_role), sql.Identifier(pg.runtime_role)
        )
    )
    pg.owner_connection.commit()

    try:
        cursor.execute(
            "SELECT pg_catalog.has_sequence_privilege(%s, %s, 'UPDATE')",
            (pg.runtime_role, f"{pg.schema}.{pg.store.sequence}"),
        )
        assert cursor.fetchone()[0] is True
        with pytest.raises(ValueError, match="member of another database role"):
            pg.owner_store.ensure_schema(runtime_role=pg.runtime_role)

        cursor = pg.owner_connection.cursor()
        cursor.execute(
            "SELECT pg_catalog.has_sequence_privilege(%s, %s, 'UPDATE')",
            (pg.runtime_role, f"{pg.schema}.{pg.store.sequence}"),
        )
        assert cursor.fetchone()[0] is True
    finally:
        pg.owner_connection.rollback()
        cursor = pg.owner_connection.cursor()
        cursor.execute(
            sql.SQL("REVOKE {} FROM {}").format(
                sql.Identifier(helper_role), sql.Identifier(pg.runtime_role)
            )
        )
        cursor.execute(
            sql.SQL("REVOKE ALL ON SEQUENCE {} FROM {}").format(
                sequence, sql.Identifier(helper_role)
            )
        )
        cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(helper_role)))
        pg.owner_connection.commit()


def test_schema_setup_rejects_noinherit_role_membership_escalation(pg: PgHarness) -> None:
    from psycopg import sql

    helper_role = f"audit_escalation_{uuid.uuid4().hex[:12]}"
    table = _relation(pg.schema, pg.store.table)
    cursor = pg.owner_connection.cursor()
    cursor.execute(
        "SELECT c.oid FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relname = %s",
        (pg.schema, pg.store.table),
    )
    table_oid = cursor.fetchone()[0]
    cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(helper_role)))
    cursor.execute(
        sql.SQL("GRANT UPDATE ON TABLE {} TO {}").format(table, sql.Identifier(helper_role))
    )
    cursor.execute(sql.SQL("ALTER ROLE {} NOINHERIT").format(sql.Identifier(pg.runtime_role)))
    cursor.execute(
        sql.SQL("GRANT {} TO {}").format(
            sql.Identifier(helper_role), sql.Identifier(pg.runtime_role)
        )
    )
    pg.owner_connection.commit()

    try:
        with pytest.raises(ValueError, match="member of another database role"):
            pg.owner_store.ensure_schema(runtime_role=pg.runtime_role)

        runtime_cursor = pg.runtime_connection.cursor()
        runtime_cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(helper_role)))
        runtime_cursor.execute(
            "SELECT current_user, pg_catalog.has_table_privilege(current_user, %s, 'UPDATE')",
            (table_oid,),
        )
        assert runtime_cursor.fetchone() == (helper_role, True)
        pg.runtime_connection.rollback()
    finally:
        pg.owner_connection.rollback()
        cursor = pg.owner_connection.cursor()
        cursor.execute(
            sql.SQL("REVOKE {} FROM {}").format(
                sql.Identifier(helper_role), sql.Identifier(pg.runtime_role)
            )
        )
        cursor.execute(
            sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(table, sql.Identifier(helper_role))
        )
        cursor.execute(sql.SQL("ALTER ROLE {} INHERIT").format(sql.Identifier(pg.runtime_role)))
        cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(helper_role)))
        pg.owner_connection.commit()


def test_owner_insert_is_bounded_by_database_metadata_constraints(pg: PgHarness) -> None:
    from psycopg import sql

    table = _relation(pg.schema, pg.store.table)
    pg.store.append(_record("before-metadata-constraint-repair"))
    cursor = pg.owner_connection.cursor()
    cursor.execute(
        sql.SQL("ALTER TABLE {} DROP CONSTRAINT audit_event_metadata_safe_check").format(table)
    )
    pg.owner_connection.commit()
    pg.owner_store.ensure_schema(runtime_role=pg.runtime_role)
    cursor.execute(sql.SQL("SELECT action FROM {} ORDER BY id").format(table))
    assert cursor.fetchall() == [("before-metadata-constraint-repair",)]

    for field, value in (
        ("actor", "é" * 129),
        ("action", " "),
        ("resource", "r" * 513),
        ("actor", "bad\nvalue"),
        ("action", "bad\x01value"),
        ("resource", "bad\u2028value"),
        ("resource", "bad\u2029value"),
    ):
        with pytest.raises(pg.driver.errors.CheckViolation):
            pg.owner_connection.cursor().execute(
                sql.SQL(
                    "INSERT INTO {} (actor, action, resource, outcome, occurred_at) "
                    "VALUES (%s, %s, %s, 'allowed', 1.0)"
                ).format(table),
                tuple(
                    value if column == field else "valid"
                    for column in ("actor", "action", "resource")
                ),
            )
        pg.owner_connection.rollback()


def test_schema_setup_rejects_malformed_preexisting_table_without_granting_access(
    pg: PgHarness,
) -> None:
    from psycopg import sql

    table = _relation(pg.schema, pg.store.table)
    sequence = _relation(pg.schema, pg.store.sequence)
    cursor = pg.owner_connection.cursor()
    cursor.execute(sql.SQL("DROP TABLE {} CASCADE").format(table))
    cursor.execute(sql.SQL("DROP SEQUENCE IF EXISTS {}").format(sequence))
    cursor.execute(sql.SQL("CREATE SEQUENCE {}").format(sequence))
    cursor.execute(
        sql.SQL(
            "CREATE TABLE {} ("
            "id BIGINT NOT NULL DEFAULT nextval({}::regclass), "
            "actor TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL, "
            "outcome TEXT NOT NULL CONSTRAINT audit_event_outcome_check "
            "CHECK (outcome <> 'denied'), occurred_at DOUBLE PRECISION NOT NULL, "
            "before_json TEXT, after_json TEXT)"
        ).format(table, sql.Literal(f"{pg.schema}.{pg.store.sequence}"))
    )
    cursor.execute(sql.SQL("ALTER SEQUENCE {} OWNED BY {}.id").format(sequence, table))
    pg.owner_connection.commit()

    with pytest.raises(RuntimeError, match="audit constraint audit_event_outcome_check"):
        pg.owner_store.ensure_schema(runtime_role=pg.runtime_role)

    cursor = pg.owner_connection.cursor()
    cursor.execute(
        "SELECT pg_catalog.has_table_privilege(%s, %s, 'INSERT')",
        (pg.runtime_role, f"{pg.schema}.{pg.store.table}"),
    )
    assert cursor.fetchone()[0] is False


def test_schema_setup_rejects_uppercase_outcome_literals_without_granting_access(
    pg: PgHarness,
) -> None:
    from psycopg import sql

    table = _relation(pg.schema, pg.store.table)
    sequence = _relation(pg.schema, pg.store.sequence)
    cursor = pg.owner_connection.cursor()
    cursor.execute(sql.SQL("DROP TABLE {} CASCADE").format(table))
    cursor.execute(sql.SQL("DROP SEQUENCE IF EXISTS {}").format(sequence))
    cursor.execute(sql.SQL("CREATE SEQUENCE {}").format(sequence))
    cursor.execute(
        sql.SQL(
            "CREATE TABLE {} ("
            "id BIGINT NOT NULL DEFAULT nextval({}::regclass), "
            "actor TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL, "
            "outcome TEXT NOT NULL CONSTRAINT audit_event_outcome_check "
            "CHECK (outcome = 'ALLOWED' OR outcome = 'DENIED'), "
            "occurred_at DOUBLE PRECISION NOT NULL, before_json TEXT, after_json TEXT)"
        ).format(table, sql.Literal(f"{pg.schema}.{pg.store.sequence}"))
    )
    cursor.execute(sql.SQL("ALTER SEQUENCE {} OWNED BY {}.id").format(sequence, table))
    pg.owner_connection.commit()

    with pytest.raises(RuntimeError, match="audit constraint audit_event_outcome_check"):
        pg.owner_store.ensure_schema(runtime_role=pg.runtime_role)

    cursor = pg.owner_connection.cursor()
    cursor.execute(
        "SELECT pg_catalog.has_table_privilege(%s, %s, 'SELECT'), "
        "pg_catalog.has_table_privilege(%s, %s, 'INSERT')",
        (
            pg.runtime_role,
            f"{pg.schema}.{pg.store.table}",
            pg.runtime_role,
            f"{pg.schema}.{pg.store.table}",
        ),
    )
    assert cursor.fetchone() == (False, False)


def test_schema_setup_rejects_extra_preexisting_column_without_granting_access(
    pg: PgHarness,
) -> None:
    from psycopg import sql

    table = _relation(pg.schema, pg.store.table)
    cursor = pg.owner_connection.cursor()
    cursor.execute(sql.SQL("ALTER TABLE {} ADD COLUMN unexpected TEXT").format(table))
    cursor.execute(
        sql.SQL("REVOKE ALL PRIVILEGES ON TABLE {} FROM {}").format(
            table, sql.Identifier(pg.runtime_role)
        )
    )
    pg.owner_connection.commit()

    with pytest.raises(RuntimeError, match="audit table has incompatible columns"):
        pg.owner_store.ensure_schema(runtime_role=pg.runtime_role)

    cursor = pg.owner_connection.cursor()
    cursor.execute(
        "SELECT pg_catalog.has_table_privilege(%s, %s, 'SELECT'), "
        "pg_catalog.has_table_privilege(%s, %s, 'INSERT')",
        (
            pg.runtime_role,
            f"{pg.schema}.{pg.store.table}",
            pg.runtime_role,
            f"{pg.schema}.{pg.store.table}",
        ),
    )
    assert cursor.fetchone() == (False, False)


def test_mixed_case_schema_and_prefix_support_schema_qualified_sequence_default(
    pg: PgHarness,
) -> None:
    from psycopg import sql

    mixed_schema = f"Audit{uuid.uuid4().hex[:8]}"
    mixed_prefix = f"ConsoleAudit{uuid.uuid4().hex[:8]}"
    owner_store = PostgresAuditStore(pg.owner_connection, prefix=mixed_prefix, schema=mixed_schema)
    runtime_store = PostgresAuditStore(
        pg.runtime_connection, prefix=mixed_prefix, schema=mixed_schema
    )

    try:
        owner_store.ensure_schema(runtime_role=pg.runtime_role)
        stored = runtime_store.append(_record("mixed-case-identifiers"))
        assert stored.sequence_id == 1
        assert runtime_store.list_events() == (stored,)
        pg.runtime_connection.commit()
    finally:
        pg.runtime_connection.rollback()
        pg.owner_connection.rollback()
        cursor = pg.owner_connection.cursor()
        cursor.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(mixed_schema))
        )
        pg.owner_connection.commit()
