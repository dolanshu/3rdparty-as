"""Append-only PostgreSQL snapshots for management-plane rules. REQ-F-12."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService

SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
_MAX_PREFIX_LENGTH = 56
_MAX_SCHEMA_LENGTH = 63
_RULE_FIELDS = {
    "rule_id",
    "name",
    "match_field",
    "match_mode",
    "match_value",
    "target_service",
    "enabled",
    "target_detail",
}


class DuplicateManagedRuleError(Exception):
    """Raised when a rule id already has a durable history."""


class StaleManagedRuleRevisionError(Exception):
    """Raised when an append does not name the current revision."""

    def __init__(self, rule_id: str, expected_revision: int, actual_revision: int) -> None:
        """Record the compare-and-swap values for the caller."""
        super().__init__(
            f"stale managed rule {rule_id!r}: expected revision {expected_revision}, "
            f"current revision is {actual_revision}"
        )
        self.rule_id = rule_id
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision


class InvalidManagedRuleSnapshotError(ValueError):
    """Raised when a requested snapshot violates managed-rule invariants."""


class ManagedRuleNotFoundError(LookupError):
    """Raised when an append targets a rule id without a history."""


@dataclass(frozen=True)
class StoredManagedRule:
    """One immutable, audited snapshot of a managed rule or deletion."""

    rule_id: str
    revision: int
    rule: ManagedRule | None
    change_id: str
    actor: str
    created_at: float

    def __post_init__(self) -> None:
        """Keep stored identity, revision, metadata, and timestamps valid."""
        _require_nonblank_text(self.rule_id, "rule_id")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("revision must be a positive integer")
        _require_nonblank_text(self.change_id, "change_id")
        _require_nonblank_text(self.actor, "actor")
        _require_finite_number(self.created_at, "created_at")
        object.__setattr__(self, "created_at", float(self.created_at))
        if self.rule is not None and type(self.rule) is not ManagedRule:
            raise TypeError("rule must be a ManagedRule or None")
        if self.rule is not None and self.rule.rule_id != self.rule_id:
            raise InvalidManagedRuleSnapshotError("rule.rule_id must match stored rule_id")


class _Cursor(Protocol):
    def execute(self, sql: str, params: tuple[object, ...] = ()) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...


class _Connection(Protocol):
    info: Any

    def cursor(self) -> _Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class ManagedRuleStore(Protocol):
    """Repository operations required by the management API boundary."""

    def create(
        self, rule: ManagedRule, change_id: str, actor: str, created_at: float
    ) -> StoredManagedRule:
        """Create a new managed-rule history at revision one."""
        ...

    def get(self, rule_id: str) -> StoredManagedRule | None:
        """Return the latest snapshot for a rule id, if present."""
        ...

    def list_latest(self) -> tuple[StoredManagedRule, ...]:
        """Return all latest snapshots, including tombstones, deterministically."""
        ...

    def history(self, rule_id: str) -> tuple[StoredManagedRule, ...]:
        """Return all snapshots for one rule id, oldest first."""
        ...

    def append(
        self,
        rule_id: str,
        rule: ManagedRule | None,
        change_id: str,
        actor: str,
        created_at: float,
        expected_revision: int,
    ) -> StoredManagedRule:
        """Append one snapshot only when the expected revision is current."""
        ...


class PostgresManagedRuleStore:
    """Persist immutable rule snapshots while advancing a lockable head row.

    The caller owns the injected DB-API connection. This store reads no clock
    and opens no socket. Event rows are inserted and selected, never mutated.
    """

    def __init__(
        self, connection: _Connection, prefix: str = "managed_rules", *, schema: str = "public"
    ) -> None:
        """Wrap an open DB-API connection and validate interpolated names."""
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
        self.guard_function = f'{qualified_schema}."as_managed_rule_events_immutable_{prefix_hash}"'
        self.head_revision_function = (
            f'{qualified_schema}."as_managed_rule_head_revision_{prefix_hash}"'
        )
        self.event_head_function = f'{qualified_schema}."as_managed_rule_event_head_{prefix_hash}"'
        self.head_revision_trigger = f"as_managed_rule_head_revision_{prefix_hash}"
        self.event_head_trigger = f"as_managed_rule_event_head_{prefix_hash}"

    @property
    def connection(self) -> _Connection:
        """Expose the injected connection for shared-transaction coordination."""
        return self._connection

    def ensure_schema(self) -> None:
        """Create the head and append-only event tables; safe to repeat."""
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {self.heads_table} ("
                "rule_id TEXT PRIMARY KEY, "
                "current_revision INTEGER NOT NULL CHECK (current_revision > 0))"
            )
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {self.events_table} ("
                "rule_id TEXT NOT NULL, "
                "revision INTEGER NOT NULL CHECK (revision > 0), "
                "snapshot_json TEXT NOT NULL, "
                "change_id TEXT NOT NULL CHECK (btrim(change_id) <> ''), "
                "actor TEXT NOT NULL CHECK (btrim(actor) <> ''), "
                "created_at DOUBLE PRECISION NOT NULL CHECK ("
                "created_at > '-Infinity'::DOUBLE PRECISION AND "
                "created_at < 'Infinity'::DOUBLE PRECISION), "
                "PRIMARY KEY (rule_id, revision), "
                f"FOREIGN KEY (rule_id) REFERENCES {self.heads_table} (rule_id))"
            )
            cursor.execute(
                f"CREATE OR REPLACE FUNCTION {self.guard_function}() "
                "RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN "
                "RAISE EXCEPTION 'managed-rule event rows are immutable' "
                "USING ERRCODE = '23514'; "
                "END; $$"
            )
            cursor.execute(
                f"CREATE OR REPLACE FUNCTION {self.head_revision_function}() "
                "RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$ "
                "DECLARE events_table TEXT; event_exists BOOLEAN; "
                "BEGIN "
                "IF NEW.current_revision::BIGINT <> OLD.current_revision::BIGINT + 1 THEN "
                "RAISE EXCEPTION 'managed-rule head revision must advance by exactly one' "
                "USING ERRCODE = '23514'; "
                "END IF; "
                "events_table := left(TG_TABLE_NAME, "
                "length(TG_TABLE_NAME) - length('_heads')) || '_events'; "
                "EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I "
                "WHERE rule_id = $1 AND revision = $2)', TG_TABLE_SCHEMA, events_table) "
                "INTO event_exists USING NEW.rule_id, NEW.current_revision; "
                "IF NOT event_exists THEN "
                "RAISE EXCEPTION 'managed-rule head revision must reference an event' "
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
                "EXECUTE format('SELECT h.current_revision, MAX(e.revision) "
                "FROM %I.%I h JOIN %I.%I e ON e.rule_id = h.rule_id "
                "WHERE h.rule_id = $1 GROUP BY h.current_revision', "
                "TG_TABLE_SCHEMA, heads_table, TG_TABLE_SCHEMA, events_table) "
                "INTO head_revision, maximum_revision USING NEW.rule_id; "
                "IF head_revision IS NULL OR head_revision IS DISTINCT FROM maximum_revision THEN "
                "RAISE EXCEPTION 'managed-rule head must match the maximum event revision' "
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
                (self.events_table, "as_managed_rule_events_immutable"),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "CREATE TRIGGER as_managed_rule_events_immutable "
                    f"BEFORE UPDATE OR DELETE ON {self.events_table} "
                    f"FOR EACH ROW EXECUTE FUNCTION {self.guard_function}()"
                )
            cursor.execute(
                "SELECT 1 FROM pg_trigger WHERE tgrelid = %s::regclass "
                "AND tgname = %s AND NOT tgisinternal",
                (self.events_table, "as_managed_rule_events_no_truncate"),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"CREATE TRIGGER as_managed_rule_events_no_truncate "
                    f"BEFORE TRUNCATE ON {self.events_table} "
                    f"FOR EACH STATEMENT EXECUTE FUNCTION {self.guard_function}()"
                )
            cursor.execute(
                "SELECT 1 FROM pg_constraint WHERE conrelid = %s::regclass AND conname = %s",
                (self.heads_table, "as_managed_rule_head_event_fk"),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"ALTER TABLE {self.heads_table} "
                    "ADD CONSTRAINT as_managed_rule_head_event_fk "
                    f"FOREIGN KEY (rule_id, current_revision) REFERENCES {self.events_table} "
                    "(rule_id, revision) DEFERRABLE INITIALLY DEFERRED"
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def create(
        self,
        rule: ManagedRule,
        change_id: str,
        actor: str,
        created_at: float,
        *,
        commit: bool = True,
    ) -> StoredManagedRule:
        """Create a new rule history at revision one."""
        try:
            if type(rule) is not ManagedRule:
                raise TypeError("rule must be a ManagedRule")
            _validate_snapshot_input(rule.rule_id, rule, change_id, actor, created_at)
            snapshot = serialize_managed_rule(rule)
            cursor = self._connection.cursor()
            cursor.execute(
                f"INSERT INTO {self.heads_table} (rule_id, current_revision) "
                "VALUES (%s, 1) ON CONFLICT (rule_id) DO NOTHING RETURNING rule_id",
                (rule.rule_id,),
            )
            if cursor.fetchone() is None:
                raise DuplicateManagedRuleError(f"managed rule {rule.rule_id!r} already exists")
            cursor.execute(
                f"INSERT INTO {self.events_table} "
                "(rule_id, revision, snapshot_json, change_id, actor, created_at) "
                "VALUES (%s, 1, %s, %s, %s, %s)",
                (rule.rule_id, snapshot, change_id, actor, created_at),
            )
            if commit:
                self._connection.commit()
        except Exception:
            if self._connection is not None:
                self._connection.rollback()
            raise
        return StoredManagedRule(rule.rule_id, 1, rule, change_id, actor, created_at)

    def get(self, rule_id: str) -> StoredManagedRule | None:
        """Return the current snapshot, including a deletion tombstone."""
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT e.rule_id, e.revision, e.snapshot_json, e.change_id, e.actor, e.created_at "
            f"FROM {self.heads_table} h JOIN {self.events_table} e "
            "ON e.rule_id = h.rule_id AND e.revision = h.current_revision "
            "WHERE h.rule_id = %s",
            (rule_id,),
        )
        row = cursor.fetchone()
        return None if row is None else _stored_rule(row)

    def list_latest(self) -> tuple[StoredManagedRule, ...]:
        """Return all current snapshots, tombstones included, by rule id."""
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT e.rule_id, e.revision, e.snapshot_json, e.change_id, e.actor, e.created_at "
            f"FROM {self.heads_table} h JOIN {self.events_table} e "
            "ON e.rule_id = h.rule_id AND e.revision = h.current_revision "
            "ORDER BY h.rule_id ASC"
        )
        return tuple(_stored_rule(row) for row in cursor.fetchall())

    def history(self, rule_id: str) -> tuple[StoredManagedRule, ...]:
        """Return every immutable snapshot for one id, oldest first."""
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT rule_id, revision, snapshot_json, change_id, actor, created_at "
            f"FROM {self.events_table} WHERE rule_id = %s ORDER BY revision ASC",
            (rule_id,),
        )
        return tuple(_stored_rule(row) for row in cursor.fetchall())

    def append(
        self,
        rule_id: str,
        rule: ManagedRule | None,
        change_id: str,
        actor: str,
        created_at: float,
        expected_revision: int,
        *,
        commit: bool = True,
    ) -> StoredManagedRule:
        """Append a snapshot after locking and comparing the current head."""
        try:
            if type(expected_revision) is not int or expected_revision < 1:
                raise ValueError("expected_revision must be a positive integer")
            _validate_snapshot_input(rule_id, rule, change_id, actor, created_at)
            snapshot = serialize_managed_rule(rule)
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT h.current_revision, e.snapshot_json FROM {self.heads_table} h "
                f"JOIN {self.events_table} e ON e.rule_id = h.rule_id "
                "AND e.revision = h.current_revision WHERE h.rule_id = %s FOR UPDATE OF h",
                (rule_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ManagedRuleNotFoundError(f"managed rule {rule_id!r} does not exist")
            actual_revision, current_json = row
            actual_revision = int(actual_revision)
            if expected_revision != actual_revision:
                raise StaleManagedRuleRevisionError(rule_id, expected_revision, actual_revision)
            current_rule = deserialize_managed_rule(current_json)
            if current_rule is None:
                raise InvalidManagedRuleSnapshotError(
                    "a deleted managed rule cannot be recreated; use a new rule_id"
                )
            new_revision = actual_revision + 1
            cursor.execute(
                f"INSERT INTO {self.events_table} "
                "(rule_id, revision, snapshot_json, change_id, actor, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (rule_id, new_revision, snapshot, change_id, actor, created_at),
            )
            cursor.execute(
                f"UPDATE {self.heads_table} SET current_revision = %s "
                "WHERE rule_id = %s AND current_revision = %s RETURNING current_revision",
                (new_revision, rule_id, actual_revision),
            )
            if cursor.fetchone() is None:
                raise StaleManagedRuleRevisionError(rule_id, expected_revision, actual_revision)
            if commit:
                self._connection.commit()
        except Exception:
            if self._connection is not None:
                self._connection.rollback()
            raise
        return StoredManagedRule(rule_id, new_revision, rule, change_id, actor, created_at)


def serialize_managed_rule(rule: ManagedRule | None) -> str:
    """Encode every managed-rule field in deterministic, versioned JSON."""
    if rule is not None and type(rule) is not ManagedRule:
        raise TypeError("rule must be a ManagedRule or None")
    rule_payload: dict[str, object] | None = None
    if rule is not None:
        rule_payload = {
            "rule_id": rule.rule_id,
            "name": rule.name,
            "match_field": rule.match_field.value,
            "match_mode": rule.match_mode.value,
            "match_value": rule.match_value,
            "target_service": rule.target_service.value,
            "enabled": rule.enabled,
            "target_detail": rule.target_detail,
        }
    encoded = json.dumps(
        {"schema_version": SCHEMA_VERSION, "rule": rule_payload},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    deserialize_managed_rule(encoded)
    return encoded


def deserialize_managed_rule(encoded: str) -> ManagedRule | None:
    """Decode a snapshot, rejecting duplicate keys and non-exact field shapes."""
    if not isinstance(encoded, str):
        raise TypeError("encoded managed rule must be a string")
    try:
        payload = json.loads(
            encoded,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonfinite_json_number,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid managed-rule JSON") from exc
    envelope = _require_object(payload, {"schema_version", "rule"}, "envelope")
    version = envelope["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ValueError(f"unsupported managed-rule schema version: {version!r}")
    if envelope["rule"] is None:
        return None
    data = _require_object(envelope["rule"], _RULE_FIELDS, "rule")
    for name in ("rule_id", "name", "match_field", "match_mode", "match_value", "target_service"):
        if type(data[name]) is not str:
            raise ValueError(f"{name} must be a string")
    if type(data["enabled"]) is not bool:
        raise ValueError("enabled must be a bool")
    target_detail = data["target_detail"]
    if target_detail is not None and type(target_detail) is not str:
        raise ValueError("target_detail must be a string or null")
    try:
        return ManagedRule(
            rule_id=data["rule_id"],
            name=data["name"],
            match_field=MatchField(data["match_field"]),
            match_mode=MatchMode(data["match_mode"]),
            match_value=data["match_value"],
            target_service=TargetService(data["target_service"]),
            enabled=data["enabled"],
            target_detail=target_detail,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid managed-rule snapshot fields") from exc


def _stored_rule(row: tuple[Any, ...]) -> StoredManagedRule:
    rule_id, revision, snapshot_json, change_id, actor, created_at = row
    rule = deserialize_managed_rule(snapshot_json)
    if rule is not None and rule.rule_id != rule_id:
        raise InvalidManagedRuleSnapshotError("snapshot rule_id does not match its event key")
    return StoredManagedRule(
        rule_id=rule_id,
        revision=int(revision),
        rule=rule,
        change_id=change_id,
        actor=actor,
        created_at=created_at,
    )


def _validate_snapshot_input(
    rule_id: str,
    rule: ManagedRule | None,
    change_id: str,
    actor: str,
    created_at: float,
) -> None:
    _require_nonblank_text(rule_id, "rule_id")
    _require_nonblank_text(change_id, "change_id")
    _require_nonblank_text(actor, "actor")
    _require_finite_number(created_at, "created_at")
    if rule is not None and type(rule) is not ManagedRule:
        raise TypeError("rule must be a ManagedRule or None")
    if rule is not None and rule.rule_id != rule_id:
        raise InvalidManagedRuleSnapshotError("rule.rule_id must match the requested rule_id")


def _require_nonblank_text(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    rejected_categories = {"Cc", "Cf", "Cs", "Zl", "Zp"}
    if any(unicodedata.category(character) in rejected_categories for character in value):
        raise ValueError(
            f"{field_name} must not contain control, format, surrogate, or "
            "line/paragraph separator characters"
        )


def _require_finite_number(value: object, field_name: str) -> None:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    if isinstance(value, int):
        number: int | float = int(value)
    elif isinstance(value, float):
        number = float(value)
    else:
        raise ValueError(f"{field_name} must be a finite number")
    try:
        finite = math.isfinite(number)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{field_name} must be a finite number")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_json_number(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _require_object(value: object, keys: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{name} must contain exactly {sorted(keys)}")
    return value
