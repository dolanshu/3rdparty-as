"""Real-PostgreSQL coverage for durable managed-rule snapshots. REQ-F-12."""

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

from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService
from as_config_service.managed_rule_store import (
    DuplicateManagedRuleError,
    InvalidManagedRuleSnapshotError,
    PostgresManagedRuleStore,
    StaleManagedRuleRevisionError,
    serialize_managed_rule,
)

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
    store: PostgresManagedRuleStore
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
    prefix = f"managed_rules_test_{uuid.uuid4().hex[:10]}"
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

        store = PostgresManagedRuleStore(connection, prefix=prefix, schema="public")
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


def _rule(rule_id: str = "rule-1", **overrides: object) -> ManagedRule:
    fields: dict[str, object] = {
        "rule_id": rule_id,
        "name": "International callers",
        "match_field": MatchField.CALLING,
        "match_mode": MatchMode.PREFIX,
        "match_value": "+8613",
        "target_service": TargetService.TRANSLATION,
        "enabled": True,
        "target_detail": None,
    }
    fields.update(overrides)
    return ManagedRule(**fields)  # type: ignore[arg-type]


def test_postgres_snapshots_are_durable_append_only_and_revision_checked(pg: PgHarness) -> None:
    pg.store.ensure_schema()
    pg.store.ensure_schema()

    first = pg.store.create(_rule(), "change-create", "ops-alice", _NOW)
    assert first.revision == 1
    assert pg.store.get("rule-1") == first
    assert pg.store.get("missing") is None
    assert pg.store.history("missing") == ()
    assert pg.store.list_latest() == (first,)

    second_rule = replace(first.rule, name="Updated callers")
    second = pg.store.append(
        "rule-1", second_rule, "change-update", "ops-bob", _NOW + 1.0, expected_revision=1
    )
    deleted = pg.store.append(
        "rule-1", None, "change-delete", "ops-carol", _NOW + 2.0, expected_revision=2
    )

    assert [stored.revision for stored in pg.store.history("rule-1")] == [1, 2, 3]
    assert pg.store.history("rule-1") == (first, second, deleted)
    assert pg.store.get("rule-1") == deleted
    assert deleted.rule is None
    assert pg.store.list_latest() == (deleted,)

    with pytest.raises(StaleManagedRuleRevisionError):
        pg.store.append(
            "rule-1", second_rule, "change-stale", "ops-alice", _NOW + 3.0, expected_revision=2
        )
    with pytest.raises(InvalidManagedRuleSnapshotError, match="cannot be recreated"):
        pg.store.append(
            "rule-1", second_rule, "change-revive", "ops-alice", _NOW + 3.0, expected_revision=3
        )

    with pytest.raises(DuplicateManagedRuleError):
        pg.store.create(_rule(), "change-duplicate", "ops-alice", _NOW + 4.0)
    assert pg.store.history("rule-1") == (first, second, deleted)


def test_postgres_rejects_event_mutations_and_missing_deferred_head_revision(
    pg: PgHarness,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    first = pg.store.create(_rule(), "change-create", "ops-alice", _NOW)
    cursor = pg.connection.cursor()

    with pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            f"UPDATE {pg.prefix}_events SET snapshot_json = %s WHERE rule_id = %s AND revision = 1",
            ("{}", first.rule_id),
        )
    pg.connection.rollback()

    with pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            f"DELETE FROM {pg.prefix}_events WHERE rule_id = %s AND revision = 1",
            (first.rule_id,),
        )
    pg.connection.rollback()

    with pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(f"TRUNCATE {pg.prefix}_events CASCADE")
    pg.connection.rollback()

    for invalid_revision in (1, 2, 3):
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute(
                f"UPDATE {pg.prefix}_heads SET current_revision = %s WHERE rule_id = %s",
                (invalid_revision, first.rule_id),
            )
        pg.connection.rollback()

    cursor.execute(
        f"INSERT INTO {pg.prefix}_heads (rule_id, current_revision) VALUES (%s, 1)",
        ("missing-event-head",),
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        pg.connection.commit()
    pg.connection.rollback()

    assert pg.store.get(first.rule_id) == first
    assert pg.store.history(first.rule_id) == (first,)


def test_postgres_rejects_head_rewind_and_unmatched_event_insert(pg: PgHarness) -> None:
    psycopg = pytest.importorskip("psycopg")
    first = pg.store.create(_rule(), "change-create", "ops-alice", _NOW)
    latest_rule = replace(first.rule, name="Updated callers")
    latest = pg.store.append(
        first.rule_id,
        latest_rule,
        "change-update",
        "ops-bob",
        _NOW + 1.0,
        expected_revision=1,
    )
    cursor = pg.connection.cursor()

    with pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            f"UPDATE {pg.prefix}_heads SET current_revision = 1 WHERE rule_id = %s",
            (first.rule_id,),
        )
    pg.connection.rollback()
    assert pg.store.get(first.rule_id) == latest

    cursor.execute(
        f"SELECT change_id, actor, created_at FROM {pg.prefix}_events "
        "WHERE rule_id = %s AND revision = %s",
        (first.rule_id, latest.revision),
    )
    change_id, actor, created_at = cursor.fetchone()
    cursor.execute(
        f"INSERT INTO {pg.prefix}_events "
        "(rule_id, revision, snapshot_json, change_id, actor, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (
            first.rule_id,
            latest.revision + 1,
            serialize_managed_rule(latest.rule),
            change_id,
            actor,
            created_at,
        ),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        pg.connection.commit()
    pg.connection.rollback()

    assert pg.store.get(first.rule_id) == latest
    assert pg.store.history(first.rule_id) == (first, latest)


def test_postgres_trigger_checks_use_the_trigger_tables_schema(pg: PgHarness) -> None:
    psycopg = pytest.importorskip("psycopg")
    cursor = pg.connection.cursor()
    cursor.execute(
        f"CREATE TABLE {pg.shadow_schema}.{pg.prefix}_heads "
        "(rule_id TEXT, current_revision INTEGER)"
    )
    cursor.execute(
        f"CREATE TABLE {pg.shadow_schema}.{pg.prefix}_events "
        "(rule_id TEXT, revision INTEGER, snapshot_json TEXT, change_id TEXT, "
        "actor TEXT, created_at DOUBLE PRECISION)"
    )
    pg.connection.commit()

    head_rule = pg.store.create(_rule("search-path-head"), "create", "ops-alice", _NOW)
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_events (rule_id, revision) VALUES (%s, 2)",
        (head_rule.rule_id,),
    )
    cursor.execute(f"SET LOCAL search_path TO {pg.shadow_schema}, {pg.table_schema}")
    with pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            f"UPDATE {pg.table_schema}.{pg.prefix}_heads SET current_revision = 2 "
            "WHERE rule_id = %s",
            (head_rule.rule_id,),
        )
    pg.connection.rollback()

    event_rule = pg.store.create(_rule("search-path-event"), "create", "ops-alice", _NOW)
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_heads "
        "(rule_id, current_revision) VALUES (%s, 2)",
        (event_rule.rule_id,),
    )
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_events (rule_id, revision) VALUES (%s, 2)",
        (event_rule.rule_id,),
    )
    cursor.execute(f"SET LOCAL search_path TO {pg.shadow_schema}, {pg.table_schema}")
    cursor.execute(
        f"INSERT INTO {pg.table_schema}.{pg.prefix}_events "
        "(rule_id, revision, snapshot_json, change_id, actor, created_at) "
        "VALUES (%s, 2, %s, %s, %s, %s)",
        (
            event_rule.rule_id,
            serialize_managed_rule(event_rule.rule),
            "change-update",
            "ops-bob",
            _NOW + 1.0,
        ),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        pg.connection.commit()
    pg.connection.rollback()

    real_rule = pg.store.create(_rule("search-path-read"), "change-create", "ops-alice", _NOW)
    shadow_rule = replace(real_rule.rule, name="Shadow callers")
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_heads (rule_id, current_revision) "
        "VALUES (%s, 1)",
        (real_rule.rule_id,),
    )
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_events "
        "(rule_id, revision, snapshot_json, change_id, actor, created_at) "
        "VALUES (%s, 1, %s, %s, %s, %s)",
        (
            real_rule.rule_id,
            serialize_managed_rule(shadow_rule),
            real_rule.change_id,
            "shadow-user",
            _NOW,
        ),
    )
    pg.connection.commit()
    cursor.execute(f"SET LOCAL search_path TO {pg.shadow_schema}, {pg.table_schema}")
    assert pg.store.get(real_rule.rule_id) == real_rule
    pg.connection.rollback()


@pytest.mark.parametrize("unsafe_text", ["ops\nalice", "ops\u202ealice"])
@pytest.mark.parametrize("field", ["change_id", "actor"])
def test_postgres_store_rejects_unsafe_metadata_before_database_access(
    unsafe_text: str, field: str
) -> None:
    store = PostgresManagedRuleStore(None)  # type: ignore[arg-type]
    metadata = {"change_id": "change-1", "actor": "ops-alice"}
    metadata[field] = unsafe_text

    with pytest.raises(ValueError):
        store.create(_rule(), created_at=_NOW, **metadata)


def test_postgres_rolls_back_invalid_create_and_append_inputs(pg: PgHarness) -> None:
    first = pg.store.create(_rule(), "change-create", "ops-alice", _NOW)

    with pytest.raises(DuplicateManagedRuleError):
        pg.store.create(_rule(), "change-duplicate", "ops-bob", _NOW + 1.0)
    with pytest.raises(InvalidManagedRuleSnapshotError, match="must match"):
        pg.store.append("rule-1", _rule("rule-other"), "change-invalid", "ops-bob", _NOW + 1.0, 1)

    assert pg.store.get(first.rule_id) == first
    assert pg.store.history(first.rule_id) == (first,)
    cursor = pg.connection.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {pg.prefix}_events")
    assert cursor.fetchone()[0] == 1
