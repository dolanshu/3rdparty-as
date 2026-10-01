"""Real PostgreSQL coverage for durable distribution snapshots. ADR-0006, REQ-NF-10."""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
import warnings
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

import psycopg
import pytest
from psycopg import sql

from as_config_service.distribution_store import (
    DistributionNotFoundError,
    DuplicateDistributionError,
    InvalidDistributionSnapshotError,
    PostgresDistributionStore,
    StaleDistributionRevisionError,
    serialize_distribution,
)
from as_config_service.distributor import (
    DistributionPlan,
    DistributionState,
    IllegalDistributionStateError,
    pending_instances,
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
    store: PostgresDistributionStore
    connection: Any
    prefix: str
    table_schema: str
    shadow_schema: str


def _is_network_unavailable(exc: BaseException) -> bool:
    if not isinstance(exc, psycopg.OperationalError):
        return False
    normalized = str(exc).lower()
    return any(marker in normalized for marker in _NETWORK_UNAVAILABLE_MESSAGES)


@pytest.fixture()
def pg() -> Iterator[PgHarness]:
    parsed = urlparse(TEST_DSN)
    connection = None
    store = None
    prefix = f"distribution_test_{uuid.uuid4().hex[:10]}"
    shadow_schema = f"{prefix}_shadow"
    try:
        try:
            connection = psycopg.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
        except psycopg.OperationalError as exc:
            if _is_network_unavailable(exc):
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

        store = PostgresDistributionStore(connection, prefix=prefix, schema="public")
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
                attempt_cleanup_statement(f"DROP SCHEMA IF EXISTS {shadow_schema} CASCADE", cursor)
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


def _plan(
    change_id: str, batches: tuple[tuple[str, ...], ...] = (("as-1", "as-2"), ("as-3",))
) -> DistributionPlan:
    return DistributionPlan(change_id, 7, batches)


def test_postgres_get_ignores_same_named_shadow_tables(pg: PgHarness) -> None:
    cursor = pg.connection.cursor()
    cursor.execute(
        f"CREATE TABLE {pg.shadow_schema}.{pg.prefix}_heads "
        "(change_id TEXT PRIMARY KEY, latest_revision INTEGER NOT NULL)"
    )
    cursor.execute(
        f"CREATE TABLE {pg.shadow_schema}.{pg.prefix}_events "
        "(change_id TEXT, revision INTEGER, snapshot_json TEXT, actor TEXT, action TEXT)"
    )
    real = pg.store.create(_plan("search-path-read"), "ops-alice", _NOW)
    shadow = replace(real, actor="shadow-user")
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_heads (change_id, latest_revision) "
        "VALUES (%s, 1)",
        (real.distribution.plan.change_id,),
    )
    cursor.execute(
        f"INSERT INTO {pg.shadow_schema}.{pg.prefix}_events "
        "(change_id, revision, snapshot_json, actor, action) VALUES (%s, 1, %s, %s, %s)",
        (
            real.distribution.plan.change_id,
            serialize_distribution(shadow),
            shadow.actor,
            shadow.action,
        ),
    )
    pg.connection.commit()
    cursor.execute(f"SET LOCAL search_path TO {pg.shadow_schema}, {pg.table_schema}")

    assert pg.store.get(real.distribution.plan.change_id) == real

    pg.connection.rollback()


def test_postgres_custom_schema_writes_ignore_hostile_search_path(pg: PgHarness) -> None:
    custom_schema = f"{pg.prefix}_custom"
    custom_prefix = f"{pg.prefix}_custom"
    cursor = pg.connection.cursor()
    cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(custom_schema)))
    pg.connection.commit()
    store = PostgresDistributionStore(pg.connection, prefix=custom_prefix, schema=custom_schema)
    shadow_heads = sql.Identifier(f"{custom_prefix}_heads")
    shadow_events = sql.Identifier(f"{custom_prefix}_events")
    try:
        store.ensure_schema()
        cursor.execute(
            sql.SQL(
                "CREATE TABLE {}.{} (change_id TEXT PRIMARY KEY, latest_revision INTEGER NOT NULL)"
            ).format(sql.Identifier(pg.shadow_schema), shadow_heads)
        )
        cursor.execute(
            sql.SQL(
                "CREATE TABLE {}.{} (change_id TEXT, revision INTEGER, "
                "snapshot_json TEXT, actor TEXT, action TEXT)"
            ).format(sql.Identifier(pg.shadow_schema), shadow_events)
        )
        cursor.execute(
            sql.SQL("SET SESSION search_path TO {}, {}, public").format(
                sql.Identifier(pg.shadow_schema), sql.Identifier(custom_schema)
            )
        )

        plan = _plan("custom-schema-write")
        created = store.create(plan, "ops-alice", _NOW)
        shadow = replace(created, actor="shadow-user")
        cursor.execute(
            sql.SQL("INSERT INTO {}.{} (change_id, latest_revision) VALUES (%s, 1)").format(
                sql.Identifier(pg.shadow_schema), shadow_heads
            ),
            (plan.change_id,),
        )
        cursor.execute(
            sql.SQL(
                "INSERT INTO {}.{} "
                "(change_id, revision, snapshot_json, actor, action) "
                "VALUES (%s, 1, %s, %s, %s)"
            ).format(sql.Identifier(pg.shadow_schema), shadow_events),
            (
                plan.change_id,
                serialize_distribution(shadow),
                shadow.actor,
                shadow.action,
            ),
        )
        pg.connection.commit()

        recorded = store.record_batch(
            plan.change_id,
            {"as-1": True, "as-2": True},
            "as-reporter",
            _NOW + 1.0,
            expected_revision=1,
        )

        assert recorded.revision == 2
        assert store.get(plan.change_id) == recorded
        assert store.get(plan.change_id) != shadow
        cursor.execute(
            f"SELECT latest_revision FROM {store.heads_table} WHERE change_id = %s",
            (plan.change_id,),
        )
        assert cursor.fetchone()[0] == 2
        cursor.execute(
            f"SELECT COUNT(*) FROM {store.events_table} WHERE change_id = %s",
            (plan.change_id,),
        )
        assert cursor.fetchone()[0] == 2
    finally:
        with suppress(BaseException):
            pg.connection.rollback()
        try:
            cursor.execute("RESET search_path")
            pg.connection.commit()
        except BaseException:
            pg.connection.rollback()
        cursor.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(custom_schema))
        )
        pg.connection.commit()
        cursor.close()


def test_postgres_journal_stages_completes_and_survives_new_store(pg: PgHarness) -> None:
    plan = _plan("co-healthy")
    created = pg.store.create(plan, "ops-alice", _NOW)

    assert pg.store.connection is pg.connection
    assert created.revision == 1
    assert created.action == "begin"
    assert created.distribution.state is DistributionState.IN_PROGRESS
    assert created.distribution.updated_at == _NOW
    assert pg.store.get("missing") is None
    assert pg.store.history("missing") == ()
    with pytest.raises(DistributionNotFoundError):
        pg.store.record_batch("missing", {"as-1": True}, "ops-alice", _NOW, 1)
    with pytest.raises(DuplicateDistributionError):
        pg.store.create(plan, "ops-bob", _NOW + 1.0)

    with pytest.raises(InvalidDistributionSnapshotError, match="exactly the current batch"):
        pg.store.record_batch(plan.change_id, {"as-1": True}, "ops-alice", _NOW, 1)
    with pytest.raises(InvalidDistributionSnapshotError, match="exactly the current batch"):
        pg.store.record_batch(
            plan.change_id,
            {"as-1": True, "as-2": True, "as-3": True},
            "ops-alice",
            _NOW,
            1,
        )

    first_batch = pg.store.record_batch(
        plan.change_id, {"as-1": True, "as-2": True}, "as-reporter", _NOW + 1.0, 1
    )
    assert first_batch.revision == 2
    assert first_batch.action == "batch_result"
    assert first_batch.distribution.state is DistributionState.IN_PROGRESS
    assert first_batch.distribution.completed_batches == 1
    assert pending_instances(first_batch.distribution) == ("as-3",)

    restarted = PostgresDistributionStore(psycopg.connect(TEST_DSN), prefix=pg.prefix)
    try:
        assert restarted.get(plan.change_id) == first_batch
        completed = restarted.record_batch(
            plan.change_id, {"as-3": True}, "as-reporter", _NOW + 2.0, 2
        )
        assert completed.revision == 3
        assert completed.distribution.state is DistributionState.COMPLETED
        assert completed.distribution.updated_at == _NOW + 2.0
        assert pending_instances(completed.distribution) == ()
        assert restarted.history(plan.change_id) == (created, first_batch, completed)
        assert restarted.list_latest() == (completed,)
        with pytest.raises(StaleDistributionRevisionError) as stale:
            restarted.record_batch(plan.change_id, {"as-3": True}, "ops-alice", _NOW + 3.0, 2)
        assert (stale.value.expected_revision, stale.value.actual_revision) == (2, 3)
    finally:
        restarted.connection.close()


def test_postgres_record_batch_cas_is_serialized_across_connections(pg: PgHarness) -> None:
    plan = _plan("concurrent-cas")
    created = pg.store.create(plan, "ops-alice", _NOW)
    winner_connection = psycopg.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    loser_connection = psycopg.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    winner_store = PostgresDistributionStore(
        winner_connection, prefix=pg.prefix, schema=pg.store.schema
    )
    loser_store = PostgresDistributionStore(
        loser_connection, prefix=pg.prefix, schema=pg.store.schema
    )
    winner_staged = threading.Event()
    release_winner = threading.Event()
    loser_started = threading.Event()
    reports = {"as-1": True, "as-2": True}
    worker_cursors = []
    winner_future = None
    loser_future = None
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="distribution-cas")

    try:
        for connection in (winner_connection, loser_connection):
            cursor = connection.cursor()
            worker_cursors.append(cursor)
            cursor.execute("SET statement_timeout = '10s'")
            connection.commit()
        pids = []
        for cursor in worker_cursors:
            cursor.execute("SELECT pg_backend_pid()")
            pids.append(cursor.fetchone()[0])

        def stage_winner() -> Any:
            try:
                staged = winner_store.record_batch(
                    plan.change_id,
                    reports,
                    "as-reporter",
                    _NOW + 1.0,
                    expected_revision=1,
                    commit=False,
                )
                winner_staged.set()
                if not release_winner.wait(timeout=8):
                    raise TimeoutError("winner was not released to commit")
                winner_connection.commit()
                return staged
            except BaseException:
                winner_connection.rollback()
                raise

        def record_loser() -> Any:
            loser_started.set()
            try:
                return loser_store.record_batch(
                    plan.change_id,
                    reports,
                    "as-reporter",
                    _NOW + 1.0,
                    expected_revision=1,
                )
            except BaseException:
                loser_connection.rollback()
                raise

        winner_future = pool.submit(stage_winner)
        if not winner_staged.wait(timeout=5):
            winner_future.result(timeout=1)
            pytest.fail("winner did not stage revision 2")

        loser_future = pool.submit(record_loser)
        assert loser_started.wait(timeout=5), "loser worker did not start"
        cursor = pg.connection.cursor()
        deadline = time.monotonic() + 5
        yield_event = threading.Event()
        try:
            while True:
                cursor.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (pids[1],)
                )
                activity = cursor.fetchone()
                if activity is not None and activity[0] == "Lock":
                    break
                if time.monotonic() >= deadline:
                    pytest.fail("loser backend did not block on a PostgreSQL lock")
                yield_event.wait(0.01)
        finally:
            cursor.close()

        release_winner.set()
        winner = winner_future.result(timeout=10)
        with pytest.raises(StaleDistributionRevisionError) as stale:
            loser_future.result(timeout=10)
        assert (stale.value.expected_revision, stale.value.actual_revision) == (1, 2)

        assert winner.revision == 2
        history = pg.store.history(plan.change_id)
        assert history == (created, winner)
        assert tuple(item.revision for item in history) == (1, 2)
        assert pg.store.get(plan.change_id) == winner
        cursor = pg.connection.cursor()
        try:
            cursor.execute(
                f"SELECT latest_revision FROM {pg.store.heads_table} WHERE change_id = %s",
                (plan.change_id,),
            )
            assert cursor.fetchone() == (2,)
            cursor.execute(
                f"SELECT revision FROM {pg.store.events_table} WHERE change_id = %s "
                "ORDER BY revision",
                (plan.change_id,),
            )
            assert tuple(row[0] for row in cursor.fetchall()) == (1, 2)
        finally:
            cursor.close()
    finally:
        release_winner.set()
        futures = tuple(future for future in (winner_future, loser_future) if future is not None)
        for future in futures:
            with suppress(BaseException):
                future.result(timeout=12)
        pool.shutdown(wait=True, cancel_futures=True)
        for cursor in worker_cursors:
            with suppress(BaseException):
                cursor.close()
        winner_connection.close()
        loser_connection.close()


def test_postgres_journal_records_automatic_and_explicit_rollback(pg: PgHarness) -> None:
    unhealthy_plan = _plan("co-unhealthy")
    pg.store.create(unhealthy_plan, "ops-alice", _NOW)
    unhealthy = pg.store.record_batch(
        unhealthy_plan.change_id,
        {"as-1": True, "as-2": False},
        "as-reporter",
        _NOW + 1.0,
        1,
    )
    assert unhealthy.distribution.state is DistributionState.ROLLED_BACK
    assert unhealthy.distribution.rollback_reason == "health check failed"
    assert unhealthy.distribution.rolled_back_to == 6
    assert pending_instances(unhealthy.distribution) == ("as-3",)
    with pytest.raises(IllegalDistributionStateError):
        pg.store.record_batch(
            unhealthy_plan.change_id, {"as-3": True}, "as-reporter", _NOW + 2.0, 2
        )

    explicit_plan = _plan("co-explicit")
    explicit_started = pg.store.create(explicit_plan, "ops-alice", _NOW)
    applied = pg.store.record_batch(
        explicit_plan.change_id,
        {"as-1": True, "as-2": True},
        "as-reporter",
        _NOW + 1.0,
        1,
    )
    rolled = pg.store.roll_back(
        explicit_plan.change_id, "operator aborted", "ops-bob", _NOW + 2.0, applied.revision
    )
    assert rolled.revision == 3
    assert rolled.action == "roll_back"
    assert rolled.distribution.state is DistributionState.ROLLED_BACK
    assert rolled.distribution.rollback_reason == "operator aborted"
    assert rolled.distribution.rolled_back_to == 6
    assert pg.store.history(explicit_plan.change_id) == (explicit_started, applied, rolled)
    assert tuple(item.distribution.plan.change_id for item in pg.store.list_latest()) == (
        "co-explicit",
        "co-unhealthy",
    )


def test_postgres_journal_guards_heads_events_and_defers_head_event_foreign_key(
    pg: PgHarness,
) -> None:
    psycopg_errors = psycopg.errors
    started = pg.store.create(_plan("co-guards"), "ops-alice", _NOW)
    cursor = pg.connection.cursor()

    with pytest.raises(psycopg_errors.CheckViolation):
        cursor.execute(
            f"UPDATE {pg.prefix}_events SET snapshot_json = %s "
            "WHERE change_id = %s AND revision = 1",
            ("{}", "co-guards"),
        )
    pg.connection.rollback()

    with pytest.raises(psycopg_errors.CheckViolation):
        cursor.execute(
            f"DELETE FROM {pg.prefix}_events WHERE change_id = %s AND revision = 1",
            ("co-guards",),
        )
    pg.connection.rollback()

    with pytest.raises(psycopg_errors.CheckViolation):
        cursor.execute(f"TRUNCATE {pg.prefix}_events CASCADE")
    pg.connection.rollback()

    cursor.execute(
        f"INSERT INTO {pg.prefix}_heads (change_id, latest_revision) VALUES (%s, %s)",
        ("co-deferred-fk", 1),
    )
    with pytest.raises(psycopg_errors.ForeignKeyViolation):
        pg.connection.commit()
    pg.connection.rollback()
    assert pg.store.get("co-guards") == started


def test_postgres_journal_rejects_head_rewind_and_unheaded_event(pg: PgHarness) -> None:
    psycopg_errors = psycopg.errors
    plan = _plan("co-head-guards")
    started = pg.store.create(plan, "ops-alice", _NOW)
    latest = pg.store.record_batch(
        plan.change_id,
        {"as-1": True, "as-2": True},
        "as-reporter",
        _NOW + 1.0,
        1,
    )
    assert latest.revision == 2
    cursor = pg.connection.cursor()

    with pytest.raises(psycopg_errors.CheckViolation):
        cursor.execute(
            f"UPDATE {pg.prefix}_heads SET latest_revision = %s WHERE change_id = %s",
            (1, plan.change_id),
        )
    pg.connection.rollback()
    assert pg.store.get(plan.change_id) == latest
    assert pg.store.history(plan.change_id) == (started, latest)

    unheaded = replace(latest, revision=3, actor="ops-alice", action="batch_result")
    cursor.execute(
        f"INSERT INTO {pg.prefix}_events "
        "(change_id, revision, snapshot_json, actor, action) VALUES (%s, %s, %s, %s, %s)",
        (
            plan.change_id,
            3,
            serialize_distribution(unheaded),
            unheaded.actor,
            unheaded.action,
        ),
    )
    with pytest.raises(psycopg_errors.CheckViolation):
        pg.connection.commit()
    pg.connection.rollback()
    assert pg.store.get(plan.change_id) == latest
    assert pg.store.history(plan.change_id) == (started, latest)


def test_postgres_commit_false_leaves_transaction_control_with_caller(pg: PgHarness) -> None:
    plan = _plan("co-uncommitted")
    staged = pg.store.create(plan, "ops-alice", _NOW, commit=False)
    assert pg.store.get(plan.change_id) == staged
    pg.connection.rollback()
    assert pg.store.get(plan.change_id) is None

    committed = pg.store.create(plan, "ops-alice", _NOW)
    staged_batch = pg.store.record_batch(
        plan.change_id,
        {"as-1": True, "as-2": True},
        "as-reporter",
        _NOW + 1.0,
        committed.revision,
        commit=False,
    )
    assert staged_batch.revision == 2
    assert pg.store.get(plan.change_id) == staged_batch
    pg.connection.rollback()
    assert pg.store.get(plan.change_id) == committed
    assert pg.store.history(plan.change_id) == (committed,)
