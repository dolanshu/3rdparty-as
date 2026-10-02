"""Append-only PostgreSQL persistence for change orders. See ADR-0006 and REQ-F-14."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

from as_config_service.change_order import (
    AuditEntry,
    ChangeOrder,
    ChangeState,
    IllegalTransitionError,
    ManagedRuleChange,
    ManagedRuleChangeAction,
    approve,
    begin_distribution,
    mark_applied,
    reject,
    roll_back,
    submit,
)
from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService
from as_platform.api.contract import ConfigBundle, RuleDTO, ToggleDTO

SCHEMA_VERSION = 2
AUDIT_ENTRY_SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
_MAX_PREFIX_LENGTH = 56
_MAX_SCHEMA_LENGTH = 63
_MANAGED_RULE_FIELDS = {
    "rule_id",
    "name",
    "match_field",
    "match_mode",
    "match_value",
    "target_service",
    "enabled",
    "target_detail",
}


class DuplicateChangeOrderError(Exception):
    """Raised when a change id already has a durable order."""


class StaleChangeOrderRevisionError(Exception):
    """Raised when an append does not name the current revision."""

    def __init__(self, change_id: str, expected_revision: int, actual_revision: int) -> None:
        """Record the stale compare-and-swap values for the caller."""
        super().__init__(
            f"stale change order {change_id!r}: expected revision "
            f"{expected_revision}, current revision is {actual_revision}"
        )
        self.change_id = change_id
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision


class InvalidChangeOrderTransitionError(ValueError):
    """Raised when a proposed snapshot is not one append-only legal transition."""


class ChangeOrderNotFoundError(LookupError):
    """Raised when an append targets a change id that has not been created."""


@dataclass(frozen=True)
class StoredChangeOrder:
    """A change-order snapshot and its monotonically increasing revision."""

    order: ChangeOrder
    revision: int

    def __post_init__(self) -> None:
        """Keep stored revisions strictly positive and integral."""
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("revision must be a positive integer")


class _Cursor(Protocol):
    def execute(self, sql: str, params: tuple[object, ...] = ()) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...


class _Connection(Protocol):
    info: Any

    def cursor(self) -> _Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class ChangeOrderStore(Protocol):
    """The operations needed by the next config-service API slice."""

    def create(self, order: ChangeOrder, *, commit: bool = True) -> StoredChangeOrder:
        """Persist a new DRAFT order at revision one."""
        ...

    def get(self, change_id: str) -> StoredChangeOrder | None:
        """Return the latest snapshot, or ``None`` when absent."""
        ...

    def list_latest(self) -> tuple[StoredChangeOrder, ...]:
        """Return each current snapshot in deterministic order."""
        ...

    def history(self, change_id: str) -> tuple[StoredChangeOrder, ...]:
        """Return all snapshots for one id, oldest first."""
        ...

    def append_transition(
        self, order: ChangeOrder, expected_revision: int, *, commit: bool = True
    ) -> StoredChangeOrder:
        """Append one transition only if the expected revision is current."""
        ...


class PostgresChangeOrderStore:
    """Persist immutable order snapshots while advancing a lockable head row.

    The caller owns the injected DB-API connection. This store reads no clock
    and opens no socket. Event rows are only inserted and selected; only the
    head/index row is updated. See ADR-0006 and REQ-F-14.
    """

    def __init__(
        self, connection: _Connection, prefix: str = "change_orders", *, schema: str = "public"
    ) -> None:
        """Wrap an open DB-API connection and validate interpolated table names."""
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
        self.guard_function = f'{qualified_schema}."as_change_order_events_immutable_{prefix_hash}"'
        self.head_revision_function = (
            f'{qualified_schema}."as_change_order_head_revision_{prefix_hash}"'
        )
        self.event_head_function = f'{qualified_schema}."as_change_order_event_head_{prefix_hash}"'
        self.head_revision_trigger = f"as_change_order_head_revision_{prefix_hash}"
        self.event_head_trigger = f"as_change_order_event_head_{prefix_hash}"

    @property
    def connection(self) -> _Connection:
        """Expose the injected connection for shared-transaction coordination."""
        return self._connection

    def ensure_schema(self) -> None:
        """Create the head and append-only event tables; safe to call repeatedly."""
        cursor = self._connection.cursor()
        try:
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
                "audit_entry_json TEXT, "
                "PRIMARY KEY (change_id, revision), "
                f"FOREIGN KEY (change_id) REFERENCES {self.heads_table} (change_id))"
            )
            cursor.execute(
                f"CREATE OR REPLACE FUNCTION {self.guard_function}() "
                "RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN "
                "RAISE EXCEPTION 'change-order event rows are immutable' "
                "USING ERRCODE = '23514'; "
                "END; $$"
            )
            cursor.execute(
                f"CREATE OR REPLACE FUNCTION {self.head_revision_function}() "
                "RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$ "
                "DECLARE events_table TEXT; event_exists BOOLEAN; "
                "BEGIN "
                "IF NEW.latest_revision::BIGINT <> OLD.latest_revision::BIGINT + 1 THEN "
                "RAISE EXCEPTION 'change-order head revision must advance by exactly one' "
                "USING ERRCODE = '23514'; "
                "END IF; "
                "events_table := left(TG_TABLE_NAME, "
                "length(TG_TABLE_NAME) - length('_heads')) || '_events'; "
                "EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I "
                "WHERE change_id = $1 AND revision = $2)', TG_TABLE_SCHEMA, events_table) "
                "INTO event_exists USING NEW.change_id, NEW.latest_revision; "
                "IF NOT event_exists THEN "
                "RAISE EXCEPTION 'change-order head revision must reference an event' "
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
                "RAISE EXCEPTION 'change-order head must match the maximum event revision' "
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
                (self.events_table, "as_change_order_events_immutable"),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"CREATE TRIGGER as_change_order_events_immutable "
                    f"BEFORE UPDATE OR DELETE ON {self.events_table} "
                    f"FOR EACH ROW EXECUTE FUNCTION {self.guard_function}()"
                )
            cursor.execute(
                "SELECT 1 FROM pg_trigger WHERE tgrelid = %s::regclass "
                "AND tgname = %s AND NOT tgisinternal",
                (self.events_table, "as_change_order_events_no_truncate"),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"CREATE TRIGGER as_change_order_events_no_truncate "
                    f"BEFORE TRUNCATE ON {self.events_table} "
                    f"FOR EACH STATEMENT EXECUTE FUNCTION {self.guard_function}()"
                )
            cursor.execute(
                "SELECT 1 FROM pg_constraint WHERE conrelid = %s::regclass AND conname = %s",
                (self.heads_table, "as_change_order_head_event_fk"),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"ALTER TABLE {self.heads_table} "
                    "ADD CONSTRAINT as_change_order_head_event_fk "
                    f"FOREIGN KEY (change_id, latest_revision) REFERENCES {self.events_table} "
                    "(change_id, revision) DEFERRABLE INITIALLY DEFERRED"
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def create(self, order: ChangeOrder, *, commit: bool = True) -> StoredChangeOrder:
        """Create a new DRAFT order as its first immutable snapshot."""
        try:
            snapshot = serialize_order(order)
            if (
                order.state is not ChangeState.DRAFT
                or order.audit
                or order.approver is not None
                or order.approved_at is not None
            ):
                raise InvalidChangeOrderTransitionError(
                    "a new change order must be a clean DRAFT without approval or audit entries"
                )

            cursor = self._connection.cursor()
            cursor.execute(
                f"INSERT INTO {self.heads_table} (change_id, latest_revision) "
                "VALUES (%s, 1) ON CONFLICT (change_id) DO NOTHING RETURNING change_id",
                (order.change_id,),
            )
            if cursor.fetchone() is None:
                raise DuplicateChangeOrderError(f"change order {order.change_id!r} already exists")
            cursor.execute(
                f"INSERT INTO {self.events_table} "
                "(change_id, revision, snapshot_json, audit_entry_json) VALUES (%s, 1, %s, NULL)",
                (order.change_id, snapshot),
            )
            if commit:
                self._connection.commit()
        except Exception:
            if self._connection is not None:
                self._connection.rollback()
            raise
        return StoredChangeOrder(order=order, revision=1)

    def get(self, change_id: str) -> StoredChangeOrder | None:
        """Read the latest snapshot for one change id."""
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT e.change_id, e.revision, e.snapshot_json FROM {self.heads_table} h "
            f"JOIN {self.events_table} e ON e.change_id = h.change_id "
            "AND e.revision = h.latest_revision WHERE h.change_id = %s",
            (change_id,),
        )
        row = cursor.fetchone()
        return None if row is None else _stored_order(row)

    def list_latest(self) -> tuple[StoredChangeOrder, ...]:
        """List current heads in stable change-id order."""
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT e.change_id, e.revision, e.snapshot_json FROM {self.heads_table} h "
            f"JOIN {self.events_table} e ON e.change_id = h.change_id "
            "AND e.revision = h.latest_revision ORDER BY h.change_id ASC"
        )
        return tuple(_stored_order(row) for row in cursor.fetchall())

    def history(self, change_id: str) -> tuple[StoredChangeOrder, ...]:
        """Read every immutable snapshot for one change id, oldest first."""
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT change_id, revision, snapshot_json FROM {self.events_table} "
            "WHERE change_id = %s ORDER BY revision ASC",
            (change_id,),
        )
        return tuple(_stored_order(row) for row in cursor.fetchall())

    def append_transition(
        self, order: ChangeOrder, expected_revision: int, *, commit: bool = True
    ) -> StoredChangeOrder:
        """Lock and compare the head, then append one validated snapshot and advance it.

        The row lock prevents two concurrent writers from appending the same
        next revision. The compare-and-swap update is a second guard against a
        stale writer; event history itself is never updated or deleted. See
        ADR-0006 and REQ-F-14.
        """
        try:
            if type(expected_revision) is not int or expected_revision < 1:
                raise ValueError("expected_revision must be a positive integer")
            snapshot = serialize_order(order)
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT h.latest_revision, e.snapshot_json FROM {self.heads_table} h "
                f"JOIN {self.events_table} e ON e.change_id = h.change_id "
                "AND e.revision = h.latest_revision WHERE h.change_id = %s FOR UPDATE OF h",
                (order.change_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ChangeOrderNotFoundError(f"change order {order.change_id!r} does not exist")
            actual_revision, current_json = row
            actual_revision = int(actual_revision)
            if expected_revision != actual_revision:
                raise StaleChangeOrderRevisionError(
                    order.change_id, expected_revision, actual_revision
                )

            current = deserialize_order(current_json)
            _validate_transition(current, order)
            new_revision = actual_revision + 1
            cursor.execute(
                f"INSERT INTO {self.events_table} "
                "(change_id, revision, snapshot_json, audit_entry_json) VALUES (%s, %s, %s, %s)",
                (
                    order.change_id,
                    new_revision,
                    snapshot,
                    serialize_audit_entry(order.audit[-1]),
                ),
            )
            cursor.execute(
                f"UPDATE {self.heads_table} SET latest_revision = %s "
                "WHERE change_id = %s AND latest_revision = %s RETURNING latest_revision",
                (new_revision, order.change_id, actual_revision),
            )
            if cursor.fetchone() is None:
                raise StaleChangeOrderRevisionError(
                    order.change_id, expected_revision, actual_revision
                )
            if commit:
                self._connection.commit()
        except Exception:
            if self._connection is not None:
                self._connection.rollback()
            raise
        return StoredChangeOrder(order=order, revision=new_revision)


def serialize_order(order: ChangeOrder) -> str:
    """Encode a typed change order in deterministic, versioned JSON."""
    if type(order) is not ChangeOrder:
        raise TypeError("order must be a ChangeOrder")
    if type(order.state) is not ChangeState or type(order.audit) is not tuple:
        raise TypeError("order state and audit must use their declared types")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "order": {
            "change_id": order.change_id,
            "state": order.state.value,
            "bundle": _bundle_payload(order.bundle),
            "created_by": _require_safe_nonblank_text(order.created_by, "created_by"),
            "created_at": order.created_at,
            "approver": (
                None
                if order.approver is None
                else _require_safe_nonblank_text(order.approver, "approver")
            ),
            "approved_at": order.approved_at,
            "audit": [_audit_payload(entry) for entry in order.audit],
            "managed_rule_change": _managed_rule_change_payload(order.managed_rule_change),
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    deserialize_order(encoded)
    return encoded


def deserialize_order(encoded: str) -> ChangeOrder:
    """Decode versioned JSON, rejecting duplicate keys and any unexpected shape."""
    if not isinstance(encoded, str):
        raise TypeError("encoded order must be a string")
    try:
        payload = json.loads(encoded, object_pairs_hook=_object_without_duplicates)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid change-order JSON") from exc
    envelope = _require_object(payload, {"schema_version", "order"}, "envelope")
    version = envelope["schema_version"]
    if type(version) is not int or version not in (1, SCHEMA_VERSION):
        raise ValueError(f"unsupported change-order schema version: {version!r}")

    order_keys = {
        "change_id",
        "state",
        "bundle",
        "created_by",
        "created_at",
        "approver",
        "approved_at",
        "audit",
    }
    if version == SCHEMA_VERSION:
        order_keys.add("managed_rule_change")
    order_data = _require_object(
        envelope["order"],
        order_keys,
        "order",
    )
    state_value = _require_string(order_data["state"], "state")
    try:
        state = ChangeState(state_value)
    except ValueError as exc:
        raise ValueError(f"unknown change state: {state_value!r}") from exc
    audit_data = _require_array(order_data["audit"], "audit")
    approver = order_data["approver"]
    if approver is not None:
        approver = _require_safe_nonblank_text(approver, "approver")
    approved_at = order_data["approved_at"]
    if approved_at is not None:
        approved_at = _require_number(approved_at, "approved_at")

    return ChangeOrder(
        change_id=_require_safe_nonblank_text(order_data["change_id"], "change_id"),
        state=state,
        bundle=_decode_bundle(order_data["bundle"]),
        created_by=_require_safe_nonblank_text(order_data["created_by"], "created_by"),
        created_at=_require_number(order_data["created_at"], "created_at"),
        approver=approver,
        approved_at=approved_at,
        audit=tuple(_decode_audit(item) for item in audit_data),
        managed_rule_change=(
            None if version == 1 else _decode_managed_rule_change(order_data["managed_rule_change"])
        ),
    )


def serialize_audit_entry(entry: AuditEntry) -> str:
    """Encode one event's audit entry using the same versioned JSON envelope."""
    payload = {
        "schema_version": AUDIT_ENTRY_SCHEMA_VERSION,
        "audit_entry": _audit_payload(entry),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    deserialize_audit_entry(encoded)
    return encoded


def deserialize_audit_entry(encoded: str) -> AuditEntry:
    """Decode a standalone audit entry with strict shape and duplicate-key checks."""
    try:
        payload = json.loads(encoded, object_pairs_hook=_object_without_duplicates)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid audit-entry JSON") from exc
    envelope = _require_object(payload, {"schema_version", "audit_entry"}, "envelope")
    if (
        type(envelope["schema_version"]) is not int
        or envelope["schema_version"] != AUDIT_ENTRY_SCHEMA_VERSION
    ):
        raise ValueError(f"unsupported audit schema version: {envelope['schema_version']!r}")
    return _decode_audit(envelope["audit_entry"])


def _bundle_payload(bundle: ConfigBundle) -> dict[str, object]:
    if type(bundle) is not ConfigBundle:
        raise TypeError("bundle must be a ConfigBundle")
    if type(bundle.rules) is not tuple or any(type(rule) is not RuleDTO for rule in bundle.rules):
        raise TypeError("bundle.rules must be a tuple of RuleDTO values")
    if type(bundle.toggles) is not tuple or any(
        type(toggle) is not ToggleDTO for toggle in bundle.toggles
    ):
        raise TypeError("bundle.toggles must be a tuple of ToggleDTO values")
    return {
        "version": bundle.version,
        "rules": [
            {
                "rule_id": rule.rule_id,
                "prefix": rule.prefix,
                "action": rule.action,
                "target": rule.target,
            }
            for rule in bundle.rules
        ],
        "toggles": [
            {
                "name": toggle.name,
                "enabled": toggle.enabled,
                "removal_condition": toggle.removal_condition,
                "scope": toggle.scope,
            }
            for toggle in bundle.toggles
        ],
    }


def _decode_bundle(value: object) -> ConfigBundle:
    data = _require_object(value, {"version", "rules", "toggles"}, "bundle")
    rules: list[RuleDTO] = []
    for item in _require_array(data["rules"], "rules"):
        rule = _require_object(item, {"rule_id", "prefix", "action", "target"}, "rule")
        target = rule["target"]
        if target is not None:
            target = _require_string(target, "rule.target")
        rules.append(
            RuleDTO(
                rule_id=_require_string(rule["rule_id"], "rule.rule_id"),
                prefix=_require_string(rule["prefix"], "rule.prefix"),
                action=_require_string(rule["action"], "rule.action"),
                target=target,
            )
        )
    toggles: list[ToggleDTO] = []
    for item in _require_array(data["toggles"], "toggles"):
        toggle = _require_object(item, {"name", "enabled", "removal_condition", "scope"}, "toggle")
        if type(toggle["enabled"]) is not bool:
            raise ValueError("toggle.enabled must be a bool")
        toggles.append(
            ToggleDTO(
                name=_require_string(toggle["name"], "toggle.name"),
                enabled=toggle["enabled"],
                removal_condition=_require_string(
                    toggle["removal_condition"], "toggle.removal_condition"
                ),
                scope=_require_string(toggle["scope"], "toggle.scope"),
            )
        )
    return ConfigBundle(
        version=_require_string(data["version"], "bundle.version"),
        rules=tuple(rules),
        toggles=tuple(toggles),
    )


def _audit_payload(entry: AuditEntry) -> dict[str, object]:
    if type(entry) is not AuditEntry:
        raise TypeError("audit entries must be AuditEntry values")
    return {
        "actor": _require_safe_nonblank_text(entry.actor, "audit.actor"),
        "action": _require_safe_nonblank_text(entry.action, "audit.action"),
        "at": entry.at,
    }


def _managed_rule_change_payload(change: ManagedRuleChange | None) -> dict[str, object] | None:
    if change is None:
        return None
    if type(change) is not ManagedRuleChange:
        raise TypeError("managed_rule_change must be a ManagedRuleChange or None")
    proposed_rule: dict[str, object] | None = None
    if change.proposed_rule is not None:
        rule = change.proposed_rule
        if type(rule) is not ManagedRule:
            raise TypeError("proposed_rule must be a ManagedRule or None")
        proposed_rule = {
            "rule_id": rule.rule_id,
            "name": rule.name,
            "match_field": rule.match_field.value,
            "match_mode": rule.match_mode.value,
            "match_value": rule.match_value,
            "target_service": rule.target_service.value,
            "enabled": rule.enabled,
            "target_detail": rule.target_detail,
        }
    return {
        "action": change.action.value,
        "rule_id": _require_safe_nonblank_text(change.rule_id, "managed_rule_change.rule_id"),
        "proposed_rule": proposed_rule,
        "expected_revision": change.expected_revision,
    }


def _decode_managed_rule_change(value: object) -> ManagedRuleChange | None:
    if value is None:
        return None
    data = _require_object(
        value,
        {"action", "rule_id", "proposed_rule", "expected_revision"},
        "managed_rule_change",
    )
    action_text = _require_string(data["action"], "managed_rule_change.action")
    try:
        action = ManagedRuleChangeAction(action_text)
    except ValueError as exc:
        raise ValueError(f"unknown managed-rule change action: {action_text!r}") from exc

    proposed_value = data["proposed_rule"]
    proposed_rule: ManagedRule | None = None
    if proposed_value is not None:
        rule_data = _require_object(proposed_value, _MANAGED_RULE_FIELDS, "proposed_rule")
        rule_id = _require_string(rule_data["rule_id"], "proposed_rule.rule_id")
        name = _require_string(rule_data["name"], "proposed_rule.name")
        match_field = _require_string(rule_data["match_field"], "proposed_rule.match_field")
        match_mode = _require_string(rule_data["match_mode"], "proposed_rule.match_mode")
        match_value = _require_string(rule_data["match_value"], "proposed_rule.match_value")
        target_service = _require_string(
            rule_data["target_service"], "proposed_rule.target_service"
        )
        if type(rule_data["enabled"]) is not bool:
            raise ValueError("proposed_rule.enabled must be a bool")
        target_detail = rule_data["target_detail"]
        if target_detail is not None:
            target_detail = _require_string(target_detail, "proposed_rule.target_detail")
        try:
            proposed_rule = ManagedRule(
                rule_id=rule_id,
                name=name,
                match_field=MatchField(match_field),
                match_mode=MatchMode(match_mode),
                match_value=match_value,
                target_service=TargetService(target_service),
                enabled=rule_data["enabled"],
                target_detail=target_detail,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid managed-rule proposal fields") from exc

    try:
        return ManagedRuleChange(
            action=action,
            rule_id=_require_safe_nonblank_text(data["rule_id"], "managed_rule_change.rule_id"),
            proposed_rule=proposed_rule,
            expected_revision=data["expected_revision"],  # type: ignore[arg-type]
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid managed-rule proposal") from exc


def _decode_audit(value: object) -> AuditEntry:
    data = _require_object(value, {"actor", "action", "at"}, "audit entry")
    return AuditEntry(
        actor=_require_safe_nonblank_text(data["actor"], "audit.actor"),
        action=_require_safe_nonblank_text(data["action"], "audit.action"),
        at=_require_number(data["at"], "audit.at"),
    )


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _require_object(value: object, keys: set[str], name: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{name} must contain exactly these fields: {sorted(keys)}")
    return value


def _require_array(value: object, name: str) -> list[object]:
    if type(value) is not list:
        raise ValueError(f"{name} must be an array")
    return value


def _require_string(value: object, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} must be a string")
    return value


def _require_safe_nonblank_text(value: object, name: str) -> str:
    text = _require_string(value, name)
    if not text.strip():
        raise ValueError(f"{name} must not be blank")
    rejected_categories = {"Cc", "Cf", "Cs", "Zl", "Zp"}
    if any(unicodedata.category(character) in rejected_categories for character in text):
        raise ValueError(
            f"{name} must not contain control, format, surrogate, or "
            "line/paragraph separator characters"
        )
    return text


def _require_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _stored_order(row: tuple[Any, ...]) -> StoredChangeOrder:
    change_id, revision, encoded = row
    if type(revision) is not int or revision < 1:
        raise ValueError("stored revision must be a positive integer")
    order = deserialize_order(encoded)
    if order.change_id != change_id:
        raise ValueError("stored change_id must match relational change_id")
    return StoredChangeOrder(order=order, revision=revision)


def _validate_transition(current: ChangeOrder, proposed: ChangeOrder) -> None:
    try:
        serialize_order(proposed)
        if len(proposed.audit) != len(current.audit) + 1:
            raise InvalidChangeOrderTransitionError(
                "transition must append exactly one audit entry"
            )
        if proposed.audit[:-1] != current.audit:
            raise InvalidChangeOrderTransitionError("existing audit entries must remain unchanged")

        entry = proposed.audit[-1]
        if current.state is ChangeState.DRAFT and proposed.state is ChangeState.SUBMITTED:
            expected = submit(current, entry.actor, entry.at)
        elif current.state is ChangeState.SUBMITTED and proposed.state is ChangeState.APPROVED:
            expected = approve(current, entry.actor, entry.at)
        elif current.state is ChangeState.SUBMITTED and proposed.state is ChangeState.REJECTED:
            reason = _transition_reason(entry.action, "reject")
            expected = reject(current, entry.actor, reason, entry.at)
        elif current.state is ChangeState.APPROVED and proposed.state is ChangeState.DISTRIBUTING:
            expected = begin_distribution(current, entry.actor, entry.at)
        elif current.state is ChangeState.DISTRIBUTING and proposed.state is ChangeState.APPLIED:
            expected = mark_applied(current, entry.actor, entry.at)
        elif current.state in (ChangeState.DISTRIBUTING, ChangeState.APPLIED) and (
            proposed.state is ChangeState.ROLLED_BACK
        ):
            reason = _transition_reason(entry.action, "roll_back")
            expected = roll_back(current, entry.actor, reason, entry.at)
        else:
            message = (
                f"unsupported change-order transition: {current.state.value} "
                f"-> {proposed.state.value}"
            )
            raise InvalidChangeOrderTransitionError(message)
        if proposed != expected:
            raise InvalidChangeOrderTransitionError(
                "snapshot must retain identity, bundle and creator fields and append "
                "one state-machine audit entry"
            )
    except (IllegalTransitionError, TypeError, ValueError) as exc:
        if isinstance(exc, InvalidChangeOrderTransitionError):
            raise
        raise InvalidChangeOrderTransitionError(str(exc)) from exc


def _transition_reason(action: str, expected_action: str) -> str:
    prefix = f"{expected_action}: "
    if not action.startswith(prefix):
        raise InvalidChangeOrderTransitionError(
            f"audit action must be {expected_action!r} with a reason"
        )
    reason = action[len(prefix) :]
    if not reason.strip():
        raise InvalidChangeOrderTransitionError(
            f"audit action must be {expected_action!r} with a reason"
        )
    return reason
