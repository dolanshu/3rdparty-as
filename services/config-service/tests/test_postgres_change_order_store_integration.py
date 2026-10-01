"""Real-PostgreSQL tests for the append-only change-order journal. ADR-0006, REQ-F-14."""

from __future__ import annotations

import os
import sys
import uuid
import warnings
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

import pytest

from as_config_service.change_order import AuditEntry, ChangeOrder, ChangeState, approve, submit
from as_config_service.change_order_store import (
    DuplicateChangeOrderError,
    PostgresChangeOrderStore,
    StaleChangeOrderRevisionError,
    deserialize_order,
    serialize_order,
)
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
    store: PostgresChangeOrderStore
    connection: Any
    prefix: str
    table_schema: str
    shadow_schema: str


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
    store = None
    prefix = f"change_orders_test_{uuid.uuid4().hex[:10]}"
    shadow_schema = f"{prefix}_shadow"
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

        store = PostgresChangeOrderStore(connection, prefix=prefix, schema="public")
        store.ensure_schema()
        cursor.execute(
            "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.oid = %s::regclass",
            (store.events_table,),
        )
        table_schema = cursor.fetchone()[0]
        cursor.execute(f"CREATE SCHEMA {shadow_schema}")
        connection.commit()
        yield PgHarness(
            store=store,
            connection=connection,
            prefix=prefix,
            table_schema=table_schema,
            shadow_schema=shadow_schema,
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
                attempt_cleanup_statement("RESET search_path", cursor)
                attempt_cleanup_statement(f"DROP SCHEMA IF EXISTS {shadow_schema} CASCADE", cursor)
                if store is not None:
                    attempt_cleanup_statement(
                        f"DROP TABLE IF EXISTS {store.events_table} CASCADE", cursor
                    )
                    attempt_cleanup_statement(f"DROP TABLE IF EXISTS {store.heads_table}", cursor)
                    attempt_cleanup_statement(
                        f"DROP FUNCTION IF EXISTS {store.guard_function}()", cursor
                    )
                    attempt_cleanup_statement(
                        f"DROP FUNCTION IF EXISTS {store.head_revision_function}()", cursor
                    )
                    attempt_cleanup_statement(
                        f"DROP FUNCTION IF EXISTS {store.event_head_function}()", cursor
                    )
            attempt_cleanup(connection.close)

        if cleanup_errors:
            details = "; ".join(f"{type(exc).__name__}: {exc}" for exc in cleanup_errors)
            message = f"PostgreSQL fixture cleanup failed: {details}"
            if primary_exception is not None:
                with suppress(BaseException):
                    warnings.warn(message, RuntimeWarning, stacklevel=2)
            else:
                raise RuntimeError(message) from cleanup_errors[0]


class _OperationalError(Exception):
    pass


class _ConfigurationError(Exception):
    pass


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_OperationalError("connection refused"), True),
        (_OperationalError("connection timeout expired"), True),
        (_OperationalError("password authentication failed; timeout policy"), False),
        (_ConfigurationError("connection refused"), False),
    ],
)
def test_postgres_skip_requires_network_operational_error(
    exc: BaseException, expected: bool
) -> None:
    assert _is_network_unavailable(exc, _OperationalError) is expected


def _draft(change_id: str = "co-pg-1") -> ChangeOrder:
    return ChangeOrder(
        change_id=change_id,
        state=ChangeState.DRAFT,
        bundle=ConfigBundle(
            version="v1",
            rules=(RuleDTO("rule-1", "+8613", "translate", "return-uas"),),
            toggles=(ToggleDTO("translation.v2", False, "remove after M6"),),
        ),
        created_by="ops-alice",
        created_at=_NOW,
    )


def test_postgres_journal_is_durable_append_only_and_revision_checked(pg: PgHarness) -> None:
    pg.store.ensure_schema()
    pg.store.ensure_schema()

    draft = _draft()
    first = pg.store.create(draft)
    assert first.revision == 1
    assert pg.store.get(draft.change_id) == first
    assert pg.store.get("missing") is None

    cursor = pg.connection.cursor()
    cursor.execute(
        f"SELECT snapshot_json FROM {pg.prefix}_events WHERE change_id = %s AND revision = 1",
        (draft.change_id,),
    )
    first_snapshot = cursor.fetchone()[0]

    submitted = submit(draft, "ops-alice", _NOW + 1.0)
    second = pg.store.append_transition(submitted, expected_revision=1)
    approved = approve(submitted, "mgr-bob", _NOW + 2.0)
    third = pg.store.append_transition(approved, expected_revision=2)

    assert [stored.revision for stored in pg.store.history(draft.change_id)] == [1, 2, 3]
    assert pg.store.history(draft.change_id) == (first, second, third)
    assert pg.store.list_latest() == (third,)
    assert PostgresChangeOrderStore(pg.connection, prefix=pg.prefix).get(draft.change_id) == third

    with pytest.raises(StaleChangeOrderRevisionError):
        pg.store.append_transition(submitted, expected_revision=1)

    cursor.execute(f"SELECT COUNT(*) FROM {pg.prefix}_events")
    assert cursor.fetchone()[0] == 3
    cursor.execute(
        f"SELECT snapshot_json FROM {pg.prefix}_events WHERE change_id = %s AND revision = 1",
        (draft.change_id,),
    )
    assert cursor.fetchone()[0] == first_snapshot
    cursor.execute(f"SELECT COUNT(*) FROM {pg.prefix}_events WHERE audit_entry_json IS NOT NULL")
    assert cursor.fetchone()[0] == 2

    with pytest.raises(DuplicateChangeOrderError, match="already exists"):
        pg.store.create(draft)


def test_postgres_rejects_event_mutations_and_missing_deferred_head_revision(
    pg: PgHarness,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    draft = _draft()
    first = pg.store.create(draft)
    cursor = pg.connection.cursor()

    with pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            f"UPDATE {pg.prefix}_events SET snapshot_json = %s "
            "WHERE change_id = %s AND revision = 1",
            ("{}", draft.change_id),
        )
    pg.connection.rollback()

    with pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            f"DELETE FROM {pg.prefix}_events WHERE change_id = %s AND revision = 1",
            (draft.change_id,),
        )
    pg.connection.rollback()

    with pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(f"TRUNCATE {pg.prefix}_events CASCADE")
    pg.connection.rollback()

    for invalid_revision in (1, 2, 3):
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute(
                f"UPDATE {pg.prefix}_heads SET latest_revision = %s WHERE change_id = %s",
                (invalid_revision, draft.change_id),
            )
        pg.connection.rollback()

    cursor.execute(
        f"INSERT INTO {pg.prefix}_heads (change_id, latest_revision) VALUES (%s, 1)",
        ("missing-event-head",),
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        pg.connection.commit()
    pg.connection.rollback()

    assert pg.store.get(draft.change_id) == first
    assert pg.store.history(draft.change_id) == (first,)


def test_postgres_rejects_head_rewind_and_unmatched_event_insert(pg: PgHarness) -> None:
    psycopg = pytest.importorskip("psycopg")
    draft = _draft()
    first = pg.store.create(draft)
    latest = pg.store.append_transition(submit(draft, "ops-alice", _NOW + 1.0), expected_revision=1)
    cursor = pg.connection.cursor()

    with pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            f"UPDATE {pg.prefix}_heads SET latest_revision = 1 WHERE change_id = %s",
            (draft.change_id,),
        )
    pg.connection.rollback()
    assert pg.store.get(draft.change_id) == latest

    cursor.execute(
        f"SELECT audit_entry_json FROM {pg.prefix}_events WHERE change_id = %s AND revision = %s",
        (draft.change_id, latest.revision),
    )
    audit_entry_json = cursor.fetchone()[0]
    cursor.execute(
        f"INSERT INTO {pg.prefix}_events "
        "(change_id, revision, snapshot_json, audit_entry_json) VALUES (%s, %s, %s, %s)",
        (
            draft.change_id,
            latest.revision + 1,
            serialize_order(latest.order),
            audit_entry_json,
        ),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        pg.connection.commit()
    pg.connection.rollback()

    assert pg.store.get(draft.change_id) == latest
    assert pg.store.history(draft.change_id) == (first, latest)


def test_postgres_trigger_checks_use_the_trigger_tables_schema(pg: PgHarness) -> None:
    psycopg = pytest.importorskip("psycopg")
    cursor = pg.connection.cursor()
    cursor.execute(
        f"CREATE TABLE {pg.shadow_schema}.{pg.prefix}_heads "
        "(change_id TEXT, latest_revision INTEGER)"
    )
    cursor.execute(
        f"CREATE TABLE {pg.shadow_schema}.{pg.prefix}_events "
        "(change_id TEXT, revision INTEGER, snapshot_json TEXT, audit_entry_json TEXT)"
    )
    pg.connection.commit()

    head_order = pg.store.create(_draft("search-path-head"))
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_events "
        "(change_id, revision, snapshot_json) VALUES (%s, 2, '{}')",
        (head_order.order.change_id,),
    )
    cursor.execute(f"SET LOCAL search_path TO {pg.shadow_schema}, {pg.table_schema}")
    with pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            f"UPDATE {pg.table_schema}.{pg.prefix}_heads SET latest_revision = 2 "
            "WHERE change_id = %s",
            (head_order.order.change_id,),
        )
    pg.connection.rollback()

    event_order = pg.store.create(_draft("search-path-event"))
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_heads "
        "(change_id, latest_revision) VALUES (%s, 2)",
        (event_order.order.change_id,),
    )
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_events "
        "(change_id, revision, snapshot_json) VALUES (%s, 2, '{}')",
        (event_order.order.change_id,),
    )
    cursor.execute(f"SET LOCAL search_path TO {pg.shadow_schema}, {pg.table_schema}")
    cursor.execute(
        f"INSERT INTO {pg.table_schema}.{pg.prefix}_events "
        "(change_id, revision, snapshot_json, audit_entry_json) VALUES (%s, 2, %s, NULL)",
        (event_order.order.change_id, serialize_order(event_order.order)),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        pg.connection.commit()
    pg.connection.rollback()

    real_order = pg.store.create(_draft("search-path-read"))
    shadow_order = replace(real_order.order, created_by="shadow-user")
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_heads (change_id, latest_revision) "
        "VALUES (%s, 1)",
        (real_order.order.change_id,),
    )
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_events "
        "(change_id, revision, snapshot_json, audit_entry_json) VALUES (%s, 1, %s, NULL)",
        (real_order.order.change_id, serialize_order(shadow_order)),
    )
    pg.connection.commit()
    cursor.execute(f"SET LOCAL search_path TO {pg.shadow_schema}, {pg.table_schema}")
    assert pg.store.get(real_order.order.change_id) == real_order
    pg.connection.rollback()


def test_postgres_reads_reject_snapshot_with_a_different_relational_change_id(
    pg: PgHarness,
) -> None:
    stored_key = "relational-change-id"
    snapshot_order = _draft("snapshot-change-id")
    cursor = pg.connection.cursor()
    cursor.execute(
        f"INSERT INTO {pg.table_schema}.{pg.prefix}_heads (change_id, latest_revision) "
        "VALUES (%s, 1)",
        (stored_key,),
    )
    cursor.execute(
        f"INSERT INTO {pg.table_schema}.{pg.prefix}_events "
        "(change_id, revision, snapshot_json, audit_entry_json) VALUES (%s, 1, %s, NULL)",
        (stored_key, serialize_order(snapshot_order)),
    )
    pg.connection.commit()

    with pytest.raises(ValueError, match="relational change_id"):
        pg.store.get(stored_key)
    with pytest.raises(ValueError, match="relational change_id"):
        pg.store.list_latest()
    with pytest.raises(ValueError, match="relational change_id"):
        pg.store.history(stored_key)


@pytest.mark.parametrize("unsafe_text", ["ops\nalice", "ops\u202ealice"])
def test_postgres_journal_rejects_unsafe_audit_metadata_before_database_access(
    unsafe_text: str,
) -> None:
    store = PostgresChangeOrderStore(None)  # type: ignore[arg-type]
    draft = _draft()

    with pytest.raises(ValueError):
        store.create(replace(draft, change_id=unsafe_text))
    with pytest.raises(ValueError):
        store.create(replace(draft, audit=(AuditEntry(unsafe_text, "submit", _NOW),)))
    with pytest.raises(ValueError):
        store.create(replace(draft, audit=(AuditEntry("ops-alice", unsafe_text, _NOW),)))


@pytest.mark.parametrize("unsafe_text", ["ops\nalice", "ops\u202ealice"])
def test_change_order_decoder_rejects_unsafe_stored_audit_metadata(unsafe_text: str) -> None:
    import json

    submitted = submit(_draft(), "ops-alice", _NOW + 1.0)
    payload = json.loads(serialize_order(submitted))
    payload["order"]["change_id"] = unsafe_text
    with pytest.raises(ValueError):
        deserialize_order(json.dumps(payload))

    payload = json.loads(serialize_order(submitted))
    payload["order"]["audit"][0]["actor"] = unsafe_text
    with pytest.raises(ValueError):
        deserialize_order(json.dumps(payload))

    payload = json.loads(serialize_order(submitted))
    payload["order"]["audit"][0]["action"] = unsafe_text
    with pytest.raises(ValueError):
        deserialize_order(json.dumps(payload))
