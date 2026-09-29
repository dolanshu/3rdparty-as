"""Integration tests for the PostgreSQL configuration version repository.

ADR-0006 puts every configuration version in PostgreSQL as an immutable row and
ADR-0007 assigns governance data to PostgreSQL and runtime state to Redis. What
this file pins is that the PostgreSQL implementation of the ``VersionStore`` seam
really behaves like the in-memory one the unit tests pin, against a **real
server**: append-only, numbered from one, history readable forever, and a version
row that is never rewritten.

The last case is the one that matters most: it walks the whole ADR-0006
governance pipeline — change order, approval, version row, staged distribution,
automatic rollback — with PostgreSQL as the repository, and asserts that the rows
in the database are what the pipeline says they are.

The DSN and the port come from the environment (``AS_PG_TEST_DSN``), never from a
hardcoded number inside a case (AGENT.md §6). A run without a reachable server
skips instead of failing: the absence of PostgreSQL is an environment fact, not a
regression.

AGENT.md §5: every timestamp below is injected by the test; no case reads a clock.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import pytest

from as_config_service.change_order import (
    ChangeOrder,
    ChangeState,
    approve,
    begin_distribution,
    mark_applied,
    roll_back,
    submit,
)
from as_config_service.distributor import (
    DistributionPlan,
    DistributionState,
    apply_batch,
    begin,
    pending_instances,
)
from as_config_service.postgres_store import PostgresVersionStore
from as_config_service.version_store import VersionStore
from as_platform.api.contract import ConfigBundle, RuleDTO, ToggleDTO, toggle_deployment

pytestmark = pytest.mark.integration

# The one place the server address is written down, and it is overridable: a
# hardcoded port inside a case would collide with a parallel run (AGENT.md §6).
TEST_DSN = os.environ.get(
    "AS_PG_TEST_DSN", "postgresql://postgres:secret@127.0.0.1:55432/as_config"
)
_CONNECT_TIMEOUT_SECONDS = 3

T0 = 1_700_000_000.0
CHANGE_ID = "co-pg-1"
BASELINE_CHANGE_ID = "co-pg-0"
SUBMITTER = "ops-alice"
APPROVER = "mgr-bob"
SWITCH = "translation.v2"
REMOVAL = "delete the switch when translation.v2 is the only path, at the latest in M6"
FIRST_BATCH = ("as-1", "as-2")
SECOND_BATCH = ("as-3",)
BATCHES = (FIRST_BATCH, SECOND_BATCH)


@dataclass(frozen=True)
class PgHarness:
    """One PostgreSQL repository, isolated to a single case.

    The table name carries a random suffix, so two runs — or two workers — never
    write into the same table (AGENT.md §6).

    Attributes:
        store: The repository under test, on a real connection.
        connection: The same connection, used to assert on raw rows.
        table: The table this case owns.
    """

    store: PostgresVersionStore
    connection: Any
    table: str

    def row_count(self) -> int:
        """How many version rows the table holds.

        Returns:
            The number of rows, read straight from PostgreSQL.
        """
        cursor = self.connection.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {self.table}")
        row = cursor.fetchone()
        assert row is not None, "COUNT(*) always returns a row"
        return int(row[0])


@pytest.fixture()
def pg() -> Iterator[PgHarness]:
    """A repository on a real PostgreSQL server, dropped again afterwards."""
    psycopg = pytest.importorskip("psycopg")

    parsed = urlparse(TEST_DSN)
    try:
        connection = psycopg.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - any failure to reach the server skips
        pytest.skip(f"no PostgreSQL server reachable at {parsed.hostname}:{parsed.port}: {exc}")

    table = f"config_versions_test_{uuid.uuid4().hex[:8]}"
    store = PostgresVersionStore(connection, table=table)
    store.ensure_schema()
    try:
        yield PgHarness(store=store, connection=connection, table=table)
    finally:
        cursor = connection.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {table}")
        connection.commit()
        connection.close()


def _bundle(version: str, enabled: bool) -> ConfigBundle:
    """A bundle carrying one rule and one switch in ``enabled`` state."""
    return ConfigBundle(
        version=version,
        rules=(
            RuleDTO(rule_id="rule-755", prefix="+86755", action="translate", target="return-uas"),
        ),
        toggles=(ToggleDTO(name=SWITCH, enabled=enabled, removal_condition=REMOVAL),),
    )


def _deployment(store: VersionStore, version: int) -> Mapping[str, bool]:
    """The switch table of ``version``, read back out of PostgreSQL."""
    stored = store.get(version)
    assert stored is not None, f"version {version} was never written"
    return toggle_deployment(stored.bundle)


def test_ensure_schema_is_idempotent(pg: PgHarness) -> None:
    """Creating the schema twice is a no-op, so a restart does not fail. See ADR-0006."""
    pg.store.ensure_schema()
    pg.store.ensure_schema()

    assert pg.row_count() == 0


def test_from_dsn_connects_and_creates_the_schema(pg: PgHarness) -> None:
    """``from_dsn`` is the production entry point; it must reach the server."""
    table = f"config_versions_test_{uuid.uuid4().hex[:8]}"
    store = PostgresVersionStore.from_dsn(TEST_DSN, table=table)
    store.ensure_schema()

    appended = store.append(_bundle("v1", enabled=False), T0)
    assert appended.version == 1

    cursor = pg.connection.cursor()
    cursor.execute(f"DROP TABLE IF EXISTS {table}")
    pg.connection.commit()


def test_appends_are_numbered_from_one_and_increment(pg: PgHarness) -> None:
    """The number comes from the rows, not from the process: 1, 2, 3. See ADR-0006."""
    first = pg.store.append(_bundle("v1", enabled=False), T0)
    second = pg.store.append(_bundle("v2", enabled=True), T0 + 1.0)
    third = pg.store.append(_bundle("v3", enabled=True), T0 + 2.0)

    assert (first.version, second.version, third.version) == (1, 2, 3)
    assert (first.created_at, second.created_at, third.created_at) == (T0, T0 + 1.0, T0 + 2.0)
    assert pg.row_count() == 3, "three appends wrote three rows into PostgreSQL"


def test_latest_is_the_last_appended_version_and_none_when_empty(pg: PgHarness) -> None:
    """``latest()`` is the head of the immutable history, and ``None`` on an empty table."""
    assert pg.store.latest() is None

    first = pg.store.append(_bundle("v1", enabled=False), T0)
    assert pg.store.latest() == first

    second = pg.store.append(_bundle("v2", enabled=True), T0 + 1.0)
    assert pg.store.latest() == second


def test_get_reads_back_the_bundle_with_its_rules_and_toggles(pg: PgHarness) -> None:
    """A rule and a switch survive the round trip through PostgreSQL unchanged."""
    bundle = _bundle("v1", enabled=True)
    appended = pg.store.append(bundle, T0)

    read_back = pg.store.get(appended.version)

    assert read_back is not None
    assert read_back.bundle == bundle, "the bundle is reconstructed field for field"
    assert read_back.bundle.rules == bundle.rules
    assert read_back.bundle.toggles == bundle.toggles
    assert read_back.bundle.toggles[0].removal_condition == REMOVAL
    assert toggle_deployment(read_back.bundle)[SWITCH] is True
    assert pg.store.get(appended.version + 1) is None


def test_appending_leaves_an_older_row_untouched(pg: PgHarness) -> None:
    """A version row is immutable: a later append rewrites nothing. See ADR-0006."""
    first = pg.store.append(_bundle("v1", enabled=False), T0, change_id=BASELINE_CHANGE_ID)

    pg.store.append(_bundle("v2", enabled=True), T0 + 1.0, change_id=CHANGE_ID)

    reread = pg.store.get(1)
    assert reread is not None
    assert reread == first, "the row is byte for byte the one that was written"
    assert reread.bundle == _bundle("v1", enabled=False)
    assert reread.created_at == T0
    assert reread.change_id == BASELINE_CHANGE_ID
    assert pg.row_count() == 2


def test_history_is_the_append_order_oldest_first(pg: PgHarness) -> None:
    """History is the append order, read back out of PostgreSQL."""
    first = pg.store.append(_bundle("v1", enabled=False), T0)
    second = pg.store.append(_bundle("v2", enabled=True), T0 + 1.0)
    third = pg.store.append(_bundle("v3", enabled=True), T0 + 2.0)

    history = pg.store.history()

    assert history == (first, second, third)
    assert tuple(row.version for row in history) == (1, 2, 3)
    assert tuple(row.bundle.version for row in history) == ("v1", "v2", "v3")


def test_the_change_order_that_wrote_a_row_is_persisted(pg: PgHarness) -> None:
    """Every row is traceable to the change order that produced it. REQ-NF-10."""
    pg.store.append(_bundle("v1", enabled=False), T0)
    second = pg.store.append(_bundle("v2", enabled=True), T0 + 1.0, change_id=CHANGE_ID)

    reread = pg.store.get(second.version)

    assert reread is not None
    assert reread.change_id == CHANGE_ID
    assert pg.store.get(1) is not None
    assert pg.store.get(1).change_id is None


def test_the_governance_closed_loop_runs_over_real_postgresql(pg: PgHarness) -> None:
    """DRAFT → APPROVED → version row → distribution → rollback, on PostgreSQL.

    This is the ADR-0006 pipeline end to end with the production repository: the
    approved change appends an immutable row, a healthy fleet completes the
    staged distribution of it, a second distribution that fails its health check
    rolls back to the previous row, and that previous row — read back out of
    PostgreSQL — carries the switch value the fleet had before the change. The
    rollback writes nothing: it moves a marker, it does not rewrite history
    (ADR-0006).
    """
    store: VersionStore = pg.store

    baseline = store.append(_bundle("v1", enabled=False), T0, change_id=BASELINE_CHANGE_ID)
    assert baseline.version == 1
    assert pg.row_count() == 1, "the baseline version is a row in PostgreSQL"

    draft = ChangeOrder(
        change_id=CHANGE_ID,
        state=ChangeState.DRAFT,
        bundle=_bundle("v2", enabled=True),
        created_by=SUBMITTER,
        created_at=T0 + 1.0,
    )
    approved = approve(submit(draft, SUBMITTER, T0 + 2.0), APPROVER, T0 + 3.0)

    assert approved.state is ChangeState.APPROVED
    assert approved.approver == APPROVER, "the approver is recorded on the order"
    assert approved.approved_at == T0 + 3.0, "so is the approval time; both are injected"
    assert [entry.action for entry in approved.audit] == ["submit", "approve"]

    appended = store.append(approved.bundle, T0 + 4.0, change_id=approved.change_id)
    assert appended.version == baseline.version + 1, "the version number comes from the rows"
    assert pg.row_count() == 2, "the approval wrote one more row into PostgreSQL"

    distributing = begin_distribution(approved, SUBMITTER, T0 + 5.0)
    plan = DistributionPlan(change_id=approved.change_id, version=appended.version, batches=BATCHES)
    started = begin(plan)

    after_first = apply_batch(started, dict.fromkeys(FIRST_BATCH, True), T0 + 6.0)
    completed = apply_batch(after_first, dict.fromkeys(SECOND_BATCH, True), T0 + 7.0)

    assert after_first.state is DistributionState.IN_PROGRESS, "the release is batch by batch"
    assert completed.state is DistributionState.COMPLETED
    assert completed.completed_batches == 2
    assert all(report.applied_version == appended.version for report in completed.reports)
    assert _deployment(store, appended.version)[SWITCH] is True

    applied = mark_applied(distributing, SUBMITTER, T0 + 8.0)
    assert applied.state is ChangeState.APPLIED

    redistributed = begin(plan)
    rolled = apply_batch(redistributed, {"as-1": True, "as-2": False}, T0 + 9.0)

    assert rolled.state is DistributionState.ROLLED_BACK
    assert rolled.rolled_back_to == baseline.version, "the remedy is the previous row"
    assert rolled.rollback_reason == "health check failed"
    assert pending_instances(rolled) == SECOND_BATCH, "the blast radius stays in this batch"

    rolled_back_order = roll_back(applied, SUBMITTER, "health check failed", T0 + 9.0)
    assert rolled_back_order.state is ChangeState.ROLLED_BACK

    target = rolled.rolled_back_to
    assert target is not None, "a rollback has somewhere to go"
    restored = store.get(target)
    assert restored is not None, "the previous row is still readable after the rollback"

    assert toggle_deployment(restored.bundle)[SWITCH] is False, "the switch is back to before"
    assert restored.bundle == _bundle("v1", enabled=False)
    assert restored.created_at == T0, "the row was never rewritten"
    assert _deployment(store, appended.version)[SWITCH] is True, "the bad row is left as it was"
    assert pg.row_count() == 2, "the rollback appended nothing: history is untouched"
    assert tuple(row.version for row in store.history()) == (1, 2)
