"""Append-only PostgreSQL journal for staged distribution results. See ADR-0006."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol

from as_config_service.distributor import (
    Distribution,
    DistributionPlan,
    DistributionState,
    IllegalDistributionStateError,
    InstanceReport,
    apply_batch,
    begin,
    roll_back,
)

SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
_MAX_PREFIX_LENGTH = 56
_MAX_SCHEMA_LENGTH = 63
_ACTIONS = frozenset({"begin", "batch_result", "roll_back"})
_REJECTED_CATEGORIES = {"Cc", "Cf", "Cs", "Zl", "Zp"}


class DuplicateDistributionError(Exception):
    """Raised when a change id already has a distribution history."""


class DistributionNotFoundError(LookupError):
    """Raised when an append targets a change id without a distribution."""


class StaleDistributionRevisionError(Exception):
    """Raised when an append does not name the current revision."""

    def __init__(self, change_id: str, expected_revision: int, actual_revision: int) -> None:
        """Record the compare-and-swap values for the caller."""
        super().__init__(
            f"stale distribution {change_id!r}: expected revision {expected_revision}, "
            f"current revision is {actual_revision}"
        )
        self.change_id = change_id
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision


class InvalidDistributionSnapshotError(ValueError):
    """Raised when a plan, snapshot, or transition violates journal invariants."""


@dataclass(frozen=True)
class StoredDistribution:
    """One immutable distribution snapshot and its journal metadata."""

    distribution: Distribution
    revision: int
    actor: str
    action: str

    def __post_init__(self) -> None:
        """Reject malformed snapshot wrappers before persistence or use."""
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("revision must be a positive integer")
        _require_safe_nonblank_text(self.actor, "actor")
        _require_action(self.action)
        if type(self.distribution) is not Distribution:
            raise TypeError("distribution must be a Distribution")
        _validate_distribution(self.distribution)


class _Cursor(Protocol):
    def execute(self, sql: str, params: tuple[object, ...] = ()) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...


class _Connection(Protocol):
    info: Any

    def cursor(self) -> _Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class PostgresDistributionStore:
    """Persist validated distribution snapshots through an injected DB-API connection.

    The connection belongs to the caller. Event rows are inserted and selected,
    never updated or deleted; the head row is the only mutable revision marker.
    """

    def __init__(
        self, connection: _Connection, prefix: str = "distributions", *, schema: str = "public"
    ) -> None:
        """Wrap an open connection and validate every interpolated SQL name."""
        if (
            not isinstance(prefix, str)
            or not _IDENTIFIER.fullmatch(prefix)
            or len(prefix) > _MAX_PREFIX_LENGTH
        ):
            raise ValueError("prefix must be a safe SQL identifier of at most 56 characters")
        if (
            not isinstance(schema, str)
            or not _IDENTIFIER.fullmatch(schema)
            or len(schema) > _MAX_SCHEMA_LENGTH
        ):
            raise ValueError("schema must be a safe SQL identifier of at most 63 characters")
        self._connection = connection
        self.prefix = prefix
        self.schema = schema
        qualified_schema = f'"{schema}"'
        prefix_hash = hashlib.sha256(prefix.encode()).hexdigest()[:12]
        self.heads_table = f'{qualified_schema}."{prefix}_heads"'
        self.events_table = f'{qualified_schema}."{prefix}_events"'
        self.guard_function = f'{qualified_schema}."as_distribution_events_immutable_{prefix_hash}"'
        self.head_revision_function = (
            f'{qualified_schema}."as_distribution_heads_revision_{prefix_hash}"'
        )
        self.event_head_function = f'{qualified_schema}."as_distribution_events_head_{prefix_hash}"'
        self.head_revision_trigger = f"as_distribution_heads_revision_{prefix_hash}"
        self.event_head_trigger = f"as_distribution_events_head_{prefix_hash}"
        self.immutable_trigger = f"as_distribution_events_immutable_{prefix_hash}"
        self.no_truncate_trigger = f"as_distribution_events_no_truncate_{prefix_hash}"

    @property
    def connection(self) -> _Connection:
        """Expose the injected connection for shared-transaction coordination."""
        return self._connection

    def ensure_schema(self) -> None:
        """Create the head and immutable event tables; safe to call repeatedly."""
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {self.heads_table} ("
                "change_id TEXT PRIMARY KEY, "
                "latest_revision INTEGER NOT NULL CHECK (latest_revision > 0))"
            )
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {self.events_table} ("
                "change_id TEXT NOT NULL, "
                "revision INTEGER NOT NULL CHECK (revision > 0), "
                "snapshot_json TEXT NOT NULL, "
                "actor TEXT NOT NULL CHECK (btrim(actor) <> ''), "
                "action TEXT NOT NULL CHECK (btrim(action) <> ''), "
                "PRIMARY KEY (change_id, revision), "
                f"FOREIGN KEY (change_id) REFERENCES {self.heads_table} (change_id))"
            )
            cursor.execute(
                f"CREATE OR REPLACE FUNCTION {self.guard_function}() "
                "RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$ "
                "BEGIN "
                "RAISE EXCEPTION 'distribution event rows are immutable' "
                "USING ERRCODE = '23514'; "
                "END; $$"
            )
            cursor.execute(
                f"CREATE OR REPLACE FUNCTION {self.head_revision_function}() "
                "RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$ "
                "DECLARE events_table TEXT; event_exists BOOLEAN; "
                "BEGIN "
                "IF NEW.latest_revision::BIGINT <> OLD.latest_revision::BIGINT + 1 THEN "
                "RAISE EXCEPTION 'distribution head revision must advance by exactly one' "
                "USING ERRCODE = '23514'; "
                "END IF; "
                "events_table := left(TG_TABLE_NAME, "
                "length(TG_TABLE_NAME) - length('_heads')) || '_events'; "
                "EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I "
                "WHERE change_id = $1 AND revision = $2)', TG_TABLE_SCHEMA, events_table) "
                "INTO event_exists USING NEW.change_id, NEW.latest_revision; "
                "IF NOT event_exists THEN "
                "RAISE EXCEPTION 'distribution head revision must reference an event' "
                "USING ERRCODE = '23514'; "
                "END IF; "
                "RETURN NEW; "
                "END; $$"
            )
            cursor.execute(
                f"CREATE OR REPLACE FUNCTION {self.event_head_function}() "
                "RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$ "
                "DECLARE head_revision INTEGER; maximum_revision INTEGER; "
                "heads_table TEXT; events_table TEXT; "
                "BEGIN "
                "heads_table := left(TG_TABLE_NAME, "
                "length(TG_TABLE_NAME) - length('_events')) || '_heads'; "
                "events_table := TG_TABLE_NAME; "
                "EXECUTE format('SELECT h.latest_revision, MAX(e.revision) "
                "FROM %I.%I h JOIN %I.%I e ON e.change_id = h.change_id "
                "WHERE h.change_id = $1 GROUP BY h.latest_revision', "
                "TG_TABLE_SCHEMA, heads_table, TG_TABLE_SCHEMA, events_table) "
                "INTO head_revision, maximum_revision USING NEW.change_id; "
                "IF head_revision IS NULL OR head_revision IS DISTINCT FROM maximum_revision THEN "
                "RAISE EXCEPTION 'distribution head must match the maximum event revision' "
                "USING ERRCODE = '23514'; "
                "END IF; "
                "RETURN NULL; "
                "END; $$"
            )
            cursor.execute(
                "SELECT 1 FROM pg_trigger WHERE tgrelid = %s::regclass "
                "AND tgname = %s AND NOT tgisinternal",
                (self.heads_table, self.head_revision_trigger),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"CREATE TRIGGER {self.head_revision_trigger} "
                    f"BEFORE UPDATE ON {self.heads_table} "
                    f"FOR EACH ROW EXECUTE FUNCTION {self.head_revision_function}()"
                )
            cursor.execute(
                "SELECT 1 FROM pg_trigger WHERE tgrelid = %s::regclass "
                "AND tgname = %s AND NOT tgisinternal",
                (self.events_table, self.event_head_trigger),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"CREATE CONSTRAINT TRIGGER {self.event_head_trigger} "
                    f"AFTER INSERT ON {self.events_table} "
                    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                    f"EXECUTE FUNCTION {self.event_head_function}()"
                )
            cursor.execute(
                "SELECT 1 FROM pg_trigger WHERE tgrelid = %s::regclass "
                "AND tgname = %s AND NOT tgisinternal",
                (self.events_table, self.immutable_trigger),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"CREATE TRIGGER {self.immutable_trigger} "
                    f"BEFORE UPDATE OR DELETE ON {self.events_table} "
                    f"FOR EACH ROW EXECUTE FUNCTION {self.guard_function}()"
                )
            cursor.execute(
                "SELECT 1 FROM pg_trigger WHERE tgrelid = %s::regclass "
                "AND tgname = %s AND NOT tgisinternal",
                (self.events_table, self.no_truncate_trigger),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"CREATE TRIGGER {self.no_truncate_trigger} "
                    f"BEFORE TRUNCATE ON {self.events_table} "
                    f"FOR EACH STATEMENT EXECUTE FUNCTION {self.guard_function}()"
                )
            cursor.execute(
                "SELECT 1 FROM pg_constraint WHERE conrelid = %s::regclass AND conname = %s",
                (self.heads_table, "as_distribution_head_event_fk"),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"ALTER TABLE {self.heads_table} "
                    "ADD CONSTRAINT as_distribution_head_event_fk "
                    f"FOREIGN KEY (change_id, latest_revision) REFERENCES {self.events_table} "
                    "(change_id, revision) DEFERRABLE INITIALLY DEFERRED"
                )
            self._connection.commit()
        except Exception:
            if self._connection is not None:
                self._connection.rollback()
            raise

    def create(
        self, plan: DistributionPlan, actor: str, now: float, *, commit: bool = True
    ) -> StoredDistribution:
        """Start and persist a fresh nonempty distribution at revision one."""
        try:
            _validate_plan(plan)
            _require_safe_nonblank_text(actor, "actor")
            timestamp = _require_number(now, "now")
            distribution = replace(begin(plan), updated_at=timestamp)
            stored = StoredDistribution(distribution, 1, actor, "begin")
            snapshot = serialize_distribution(stored)
            cursor = self._connection.cursor()
            cursor.execute(
                f"INSERT INTO {self.heads_table} (change_id, latest_revision) "
                "VALUES (%s, 1) ON CONFLICT (change_id) DO NOTHING RETURNING change_id",
                (plan.change_id,),
            )
            if cursor.fetchone() is None:
                raise DuplicateDistributionError(f"distribution {plan.change_id!r} already exists")
            cursor.execute(
                f"INSERT INTO {self.events_table} "
                "(change_id, revision, snapshot_json, actor, action) "
                "VALUES (%s, 1, %s, %s, %s)",
                (plan.change_id, snapshot, actor, "begin"),
            )
            if commit:
                self._connection.commit()
        except Exception:
            if self._connection is not None:
                self._connection.rollback()
            raise
        return stored

    def get(self, change_id: str) -> StoredDistribution | None:
        """Return the latest snapshot for a change id, or ``None`` when absent."""
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT e.change_id, e.revision, e.snapshot_json, e.actor, e.action "
                f"FROM {self.heads_table} h JOIN {self.events_table} e "
                "ON e.change_id = h.change_id AND e.revision = h.latest_revision "
                "WHERE h.change_id = %s",
                (change_id,),
            )
            row = cursor.fetchone()
            return None if row is None else _stored_distribution(row)
        except Exception:
            if self._connection is not None:
                self._connection.rollback()
            raise

    def list_latest(self) -> tuple[StoredDistribution, ...]:
        """List current snapshots in stable change-id order."""
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT e.change_id, e.revision, e.snapshot_json, e.actor, e.action "
                f"FROM {self.heads_table} h JOIN {self.events_table} e "
                "ON e.change_id = h.change_id AND e.revision = h.latest_revision "
                "ORDER BY h.change_id ASC"
            )
            return tuple(_stored_distribution(row) for row in cursor.fetchall())
        except Exception:
            if self._connection is not None:
                self._connection.rollback()
            raise

    def history(self, change_id: str) -> tuple[StoredDistribution, ...]:
        """Return a complete validated event chain, oldest first."""
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT change_id, revision, snapshot_json, actor, action "
                f"FROM {self.events_table} WHERE change_id = %s ORDER BY revision ASC",
                (change_id,),
            )
            records = tuple(_stored_distribution(row) for row in cursor.fetchall())
            if records:
                if records[0].revision != 1:
                    raise InvalidDistributionSnapshotError("history must start at revision one")
                for previous, current in zip(records, records[1:], strict=False):
                    if current.revision != previous.revision + 1:
                        raise InvalidDistributionSnapshotError(
                            "history revisions must be contiguous"
                        )
                    _validate_transition(previous, current)
                if records[0].action != "begin":
                    raise InvalidDistributionSnapshotError("revision one action must be begin")
            return records
        except Exception:
            if self._connection is not None:
                self._connection.rollback()
            raise

    def record_batch(
        self,
        change_id: str,
        reports: Mapping[str, bool],
        actor: str,
        now: float,
        expected_revision: int,
        *,
        commit: bool = True,
    ) -> StoredDistribution:
        """Record exactly the current batch's observed bool results and advance the head."""
        try:
            _validate_append_metadata(change_id, actor, now, expected_revision)
            if not isinstance(reports, Mapping):
                raise TypeError("reports must be a mapping of instance ids to bool results")
            if any(type(value) is not bool for value in reports.values()):
                raise InvalidDistributionSnapshotError("every report result must be an actual bool")
            current, cursor = self._locked_current(change_id, expected_revision)
            _require_actionable(current, "batch_result")
            batch = current.distribution.plan.batches[current.distribution.completed_batches]
            if set(reports) != set(batch) or len(reports) != len(batch):
                raise InvalidDistributionSnapshotError(
                    "reports must contain exactly the current batch membership"
                )
            timestamp = _require_number(now, "now")
            distribution = replace(
                apply_batch(current.distribution, reports, timestamp), updated_at=timestamp
            )
            return self._append(
                cursor, current, change_id, distribution, actor, "batch_result", commit
            )
        except Exception:
            if self._connection is not None:
                self._connection.rollback()
            raise

    def roll_back(
        self,
        change_id: str,
        reason: str,
        actor: str,
        now: float,
        expected_revision: int,
        *,
        commit: bool = True,
    ) -> StoredDistribution:
        """Append an explicit rollback transition with a required nonblank reason."""
        try:
            _validate_append_metadata(change_id, actor, now, expected_revision)
            _require_safe_nonblank_text(reason, "reason")
            current, cursor = self._locked_current(change_id, expected_revision)
            _require_actionable(current, "roll_back")
            timestamp = _require_number(now, "now")
            distribution = replace(
                roll_back(current.distribution, reason, timestamp), updated_at=timestamp
            )
            return self._append(
                cursor, current, change_id, distribution, actor, "roll_back", commit
            )
        except Exception:
            self._connection.rollback()
            raise

    def _locked_current(
        self, change_id: str, expected_revision: int
    ) -> tuple[StoredDistribution, _Cursor]:
        """Lock the head row and reject absent or stale writers."""
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT latest_revision FROM {self.heads_table} WHERE change_id = %s FOR UPDATE",
            (change_id,),
        )
        head_row = cursor.fetchone()
        if head_row is None:
            raise DistributionNotFoundError(f"distribution {change_id!r} does not exist")
        locked_revision = head_row[0]
        if expected_revision != locked_revision:
            raise StaleDistributionRevisionError(change_id, expected_revision, locked_revision)
        cursor.execute(
            f"SELECT change_id, revision, snapshot_json, actor, action "
            f"FROM {self.events_table} WHERE change_id = %s AND revision = %s",
            (change_id, locked_revision),
        )
        event_row = cursor.fetchone()
        if event_row is None:
            raise InvalidDistributionSnapshotError(
                f"distribution {change_id!r} head references missing revision {locked_revision}"
            )
        current = _stored_distribution(event_row)
        return current, cursor

    def _append(
        self,
        cursor: _Cursor,
        current: StoredDistribution,
        change_id: str,
        distribution: Distribution,
        actor: str,
        action: str,
        commit: bool,
    ) -> StoredDistribution:
        """Validate a state-machine transition, insert its event, and CAS the head."""
        revision = current.revision + 1
        stored = StoredDistribution(distribution, revision, actor, action)
        _validate_transition(current, stored)
        cursor.execute(
            f"INSERT INTO {self.events_table} "
            "(change_id, revision, snapshot_json, actor, action) VALUES (%s, %s, %s, %s, %s)",
            (change_id, revision, serialize_distribution(stored), actor, action),
        )
        cursor.execute(
            f"UPDATE {self.heads_table} SET latest_revision = %s "
            "WHERE change_id = %s AND latest_revision = %s RETURNING latest_revision",
            (revision, change_id, current.revision),
        )
        if cursor.fetchone() is None:
            raise StaleDistributionRevisionError(change_id, current.revision, current.revision)
        if commit:
            self._connection.commit()
        return stored


def serialize_distribution(stored: StoredDistribution) -> str:
    """Encode a complete event snapshot as deterministic, versioned JSON."""
    if type(stored) is not StoredDistribution:
        raise TypeError("stored must be a StoredDistribution")
    _validate_distribution(stored.distribution)
    _validate_event_snapshot(stored)
    payload = {
        "action": _require_action(stored.action),
        "actor": _require_safe_nonblank_text(stored.actor, "actor"),
        "distribution": _distribution_payload(stored.distribution),
        "revision": stored.revision,
        "schema_version": SCHEMA_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    deserialize_distribution(encoded)
    return encoded


def deserialize_distribution(encoded: str) -> StoredDistribution:
    """Decode a strict versioned snapshot, rejecting duplicate JSON keys."""
    if type(encoded) is not str:
        raise TypeError("encoded distribution must be a string")
    try:
        payload = json.loads(
            encoded,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid distribution JSON") from exc
    envelope = _require_object(
        payload,
        {"schema_version", "revision", "actor", "action", "distribution"},
        "envelope",
    )
    version = envelope["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ValueError(f"unsupported distribution schema version: {version!r}")
    revision = envelope["revision"]
    if type(revision) is not int or revision < 1:
        raise ValueError("revision must be a positive integer")
    stored = StoredDistribution(
        _decode_distribution(envelope["distribution"]),
        revision,
        _require_safe_nonblank_text(envelope["actor"], "actor"),
        _require_action(envelope["action"]),
    )
    _validate_event_snapshot(stored)
    return stored


def _validate_event_snapshot(stored: StoredDistribution) -> None:
    distribution = stored.distribution
    if stored.revision == 1:
        if (
            stored.action != "begin"
            or distribution.state is not DistributionState.IN_PROGRESS
            or distribution.completed_batches != 0
            or distribution.reports
            or distribution.rolled_back_to is not None
            or distribution.rollback_reason is not None
        ):
            raise InvalidDistributionSnapshotError(
                "revision one must be a fresh IN_PROGRESS begin snapshot"
            )
    elif stored.action == "begin":
        raise InvalidDistributionSnapshotError("begin is only valid at revision one")
    if stored.action == "roll_back" and distribution.state is not DistributionState.ROLLED_BACK:
        raise InvalidDistributionSnapshotError("roll_back action requires ROLLED_BACK state")


def _distribution_payload(distribution: Distribution) -> dict[str, object]:
    return {
        "completed_batches": distribution.completed_batches,
        "plan": {
            "batches": [list(batch) for batch in distribution.plan.batches],
            "change_id": distribution.plan.change_id,
            "version": distribution.plan.version,
        },
        "reports": [
            {
                "applied_version": report.applied_version,
                "healthy": report.healthy,
                "instance_id": report.instance_id,
            }
            for report in distribution.reports
        ],
        "rollback_reason": distribution.rollback_reason,
        "rolled_back_to": distribution.rolled_back_to,
        "state": distribution.state.value,
        "updated_at": distribution.updated_at,
    }


def _decode_distribution(value: object) -> Distribution:
    data = _require_object(
        value,
        {
            "plan",
            "state",
            "completed_batches",
            "reports",
            "rolled_back_to",
            "rollback_reason",
            "updated_at",
        },
        "distribution",
    )
    plan_data = _require_object(data["plan"], {"change_id", "version", "batches"}, "plan")
    batches: list[tuple[str, ...]] = []
    for index, item in enumerate(_require_array(plan_data["batches"], "plan.batches")):
        batch = tuple(
            _require_safe_nonblank_text(instance, f"plan.batches[{index}] instance_id")
            for instance in _require_array(item, f"plan.batches[{index}]")
        )
        batches.append(batch)
    plan = DistributionPlan(
        _require_safe_nonblank_text(plan_data["change_id"], "plan.change_id"),
        _require_positive_int(plan_data["version"], "plan.version"),
        tuple(batches),
    )
    _validate_plan(plan)
    try:
        state = DistributionState(_require_string(data["state"], "state"))
    except ValueError as exc:
        raise ValueError(f"unknown distribution state: {data['state']!r}") from exc
    reports: list[InstanceReport] = []
    for item in _require_array(data["reports"], "reports"):
        report = _require_object(item, {"instance_id", "applied_version", "healthy"}, "report")
        healthy = report["healthy"]
        if type(healthy) is not bool:
            raise ValueError("report.healthy must be a bool")
        reports.append(
            InstanceReport(
                _require_safe_nonblank_text(report["instance_id"], "report.instance_id"),
                _require_positive_int(report["applied_version"], "report.applied_version"),
                healthy,
            )
        )
    completed = data["completed_batches"]
    if type(completed) is not int or completed < 0:
        raise ValueError("completed_batches must be a nonnegative integer")
    rolled_back_to = data["rolled_back_to"]
    if rolled_back_to is not None:
        rolled_back_to = _require_positive_int(rolled_back_to, "rolled_back_to")
    reason = data["rollback_reason"]
    if reason is not None:
        reason = _require_safe_nonblank_text(reason, "rollback_reason")
    updated_at_value = data["updated_at"]
    updated_at = (
        None if updated_at_value is None else _require_number(updated_at_value, "updated_at")
    )
    distribution = Distribution(
        plan=plan,
        state=state,
        completed_batches=completed,
        reports=tuple(reports),
        rolled_back_to=rolled_back_to,
        rollback_reason=reason,
        updated_at=updated_at,
    )
    _validate_distribution(distribution)
    return distribution


def _validate_plan(plan: DistributionPlan) -> None:
    if type(plan) is not DistributionPlan:
        raise TypeError("plan must be a DistributionPlan")
    _require_safe_nonblank_text(plan.change_id, "change_id")
    _require_positive_int(plan.version, "version")
    if type(plan.batches) is not tuple:
        raise InvalidDistributionSnapshotError("plan.batches must be a tuple")
    if not plan.batches:
        raise InvalidDistributionSnapshotError("a persisted distribution needs at least one batch")
    seen: set[str] = set()
    for index, batch in enumerate(plan.batches):
        if type(batch) is not tuple or not batch:
            raise InvalidDistributionSnapshotError(f"batch {index} must be a nonempty tuple")
        for instance_id in batch:
            _require_safe_nonblank_text(instance_id, "instance_id")
            if instance_id in seen:
                raise InvalidDistributionSnapshotError(
                    f"instance {instance_id!r} appears more than once in the plan"
                )
            seen.add(instance_id)


def _validate_distribution(distribution: Distribution) -> None:
    if type(distribution) is not Distribution:
        raise TypeError("distribution must be a Distribution")
    _validate_plan(distribution.plan)
    if type(distribution.state) is not DistributionState:
        raise InvalidDistributionSnapshotError("state must be a DistributionState")
    if distribution.state is DistributionState.PENDING:
        raise InvalidDistributionSnapshotError("PENDING distributions cannot be persisted")
    if type(distribution.completed_batches) is not int or not (
        0 <= distribution.completed_batches <= len(distribution.plan.batches)
    ):
        raise InvalidDistributionSnapshotError("completed_batches is outside the plan")
    if type(distribution.reports) is not tuple:
        raise InvalidDistributionSnapshotError("reports must be a tuple")
    ids: list[str] = []
    for report in distribution.reports:
        if type(report) is not InstanceReport:
            raise InvalidDistributionSnapshotError("reports must contain InstanceReport values")
        _require_safe_nonblank_text(report.instance_id, "report.instance_id")
        _require_positive_int(report.applied_version, "report.applied_version")
        if report.applied_version != distribution.plan.version:
            raise InvalidDistributionSnapshotError("report version must match plan version")
        if type(report.healthy) is not bool:
            raise InvalidDistributionSnapshotError("report.healthy must be a bool")
        ids.append(report.instance_id)
    if len(ids) != len(set(ids)):
        raise InvalidDistributionSnapshotError("an instance may report only once")
    complete_ids = tuple(
        instance_id
        for batch in distribution.plan.batches[: distribution.completed_batches]
        for instance_id in batch
    )
    reported_ids = tuple(ids)
    if reported_ids[: len(complete_ids)] != complete_ids:
        raise InvalidDistributionSnapshotError("reports must preserve completed batch order")
    trailing = reported_ids[len(complete_ids) :]
    if trailing:
        if distribution.completed_batches >= len(distribution.plan.batches):
            raise InvalidDistributionSnapshotError("reports exceed the planned batches")
        expected_failed_batch = distribution.plan.batches[distribution.completed_batches]
        if (
            distribution.state is not DistributionState.ROLLED_BACK
            or trailing != expected_failed_batch
        ):
            raise InvalidDistributionSnapshotError("reports may only include one failed batch")
    if distribution.state is DistributionState.IN_PROGRESS:
        if trailing or distribution.completed_batches >= len(distribution.plan.batches):
            raise InvalidDistributionSnapshotError("IN_PROGRESS must have a pending batch")
        if any(not report.healthy for report in distribution.reports):
            raise InvalidDistributionSnapshotError("IN_PROGRESS reports must all be healthy")
    elif distribution.state is DistributionState.COMPLETED:
        if distribution.completed_batches != len(distribution.plan.batches) or trailing:
            raise InvalidDistributionSnapshotError("COMPLETED requires every batch")
        if any(not report.healthy for report in distribution.reports):
            raise InvalidDistributionSnapshotError("COMPLETED reports must all be healthy")
    else:
        if distribution.rolled_back_to != (distribution.plan.version - 1 or None):
            raise InvalidDistributionSnapshotError("rollback target must precede the plan version")
        _require_safe_nonblank_text(distribution.rollback_reason, "rollback_reason")
        if trailing and distribution.rollback_reason != "health check failed":
            raise InvalidDistributionSnapshotError(
                "only an unhealthy batch may add rollback reports"
            )
        if trailing and all(report.healthy for report in distribution.reports[-len(trailing) :]):
            raise InvalidDistributionSnapshotError(
                "a failed batch must include an unhealthy result"
            )
    if distribution.state is not DistributionState.ROLLED_BACK and (
        distribution.rolled_back_to is not None or distribution.rollback_reason is not None
    ):
        raise InvalidDistributionSnapshotError("rollback fields are only valid after rollback")
    if distribution.updated_at is None:
        raise InvalidDistributionSnapshotError("persisted distributions require updated_at")
    _require_number(distribution.updated_at, "updated_at")


def _validate_transition(previous: StoredDistribution, current: StoredDistribution) -> None:
    if current.distribution.plan.change_id != previous.distribution.plan.change_id:
        raise InvalidDistributionSnapshotError("plan change_id cannot change in history")
    if current.distribution.plan != previous.distribution.plan:
        raise InvalidDistributionSnapshotError("distribution plan cannot change in history")
    if current.revision != previous.revision + 1:
        raise InvalidDistributionSnapshotError("distribution revisions must advance by one")
    if current.action == "batch_result":
        old = previous.distribution
        if old.state is not DistributionState.IN_PROGRESS:
            raise InvalidDistributionSnapshotError("batch results require IN_PROGRESS")
        batch = old.plan.batches[old.completed_batches]
        added = current.distribution.reports[len(old.reports) :]
        if tuple(report.instance_id for report in added) != batch:
            raise InvalidDistributionSnapshotError(
                "batch result must append exactly the current batch in plan order"
            )
        results = {report.instance_id: report.healthy for report in added}
        expected = apply_batch(
            old, results, _require_number(current.distribution.updated_at, "updated_at")
        )
        if current.distribution != expected:
            raise InvalidDistributionSnapshotError(
                "batch snapshot is not the pure transition result"
            )
    elif current.action == "roll_back":
        old = previous.distribution
        if old.state is not DistributionState.IN_PROGRESS:
            raise InvalidDistributionSnapshotError("rollback requires IN_PROGRESS")
        reason = current.distribution.rollback_reason
        if reason is None:
            raise InvalidDistributionSnapshotError("rollback reason is required")
        expected = roll_back(
            old, reason, _require_number(current.distribution.updated_at, "updated_at")
        )
        if current.distribution != expected:
            raise InvalidDistributionSnapshotError(
                "rollback snapshot is not the pure transition result"
            )
    else:
        raise InvalidDistributionSnapshotError("only revision one may have action begin")


def _require_action(value: object) -> str:
    action = _require_string(value, "action")
    _require_safe_nonblank_text(action, "action")
    if action not in _ACTIONS:
        raise InvalidDistributionSnapshotError(f"unsupported distribution action: {action!r}")
    return action


def _require_actionable(stored: StoredDistribution, action: str) -> None:
    if stored.action == "begin" and stored.revision != 1:
        raise InvalidDistributionSnapshotError("begin is only valid at revision one")
    if stored.distribution.state is not DistributionState.IN_PROGRESS:
        raise IllegalDistributionStateError(stored.distribution.state)
    _require_action(action)


def _validate_append_metadata(
    change_id: str, actor: str, now: float, expected_revision: int
) -> None:
    _require_safe_nonblank_text(change_id, "change_id")
    _require_safe_nonblank_text(actor, "actor")
    _require_number(now, "now")
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValueError("expected_revision must be a positive integer")


def _require_safe_nonblank_text(value: object, name: str) -> str:
    text = _require_string(value, name)
    if not text.strip():
        raise ValueError(f"{name} must not be blank")
    if any(unicodedata.category(character) in _REJECTED_CATEGORIES for character in text):
        raise ValueError(f"{name} contains unsafe metadata characters")
    return text


def _require_string(value: object, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} must be a string")
    return value


def _require_positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _require_number(value: object, name: str) -> float:
    if type(value) is int:
        return float(value)
    if type(value) is float and math.isfinite(value):
        return value
    else:
        raise ValueError(f"{name} must be a finite number")


def _require_object(value: object, keys: set[str], name: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{name} must contain exactly these fields: {sorted(keys)}")
    return value


def _require_array(value: object, name: str) -> list[object]:
    if type(value) is not list:
        raise ValueError(f"{name} must be an array")
    return value


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _stored_distribution(row: tuple[Any, ...]) -> StoredDistribution:
    change_id, revision, encoded, actor, action = row
    if type(change_id) is not str:
        raise InvalidDistributionSnapshotError("stored change_id must be a string")
    stored = deserialize_distribution(encoded)
    if stored.revision != revision:
        raise InvalidDistributionSnapshotError("snapshot revision does not match event row")
    if stored.actor != actor or stored.action != action:
        raise InvalidDistributionSnapshotError("snapshot metadata does not match event row")
    if stored.distribution.plan.change_id != change_id:
        raise InvalidDistributionSnapshotError("plan change_id does not match journal key")
    return stored
