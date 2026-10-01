"""PostgreSQL-backed append-only console audit events. See ADR-0024 and REQ-S-4."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

from as_console.access import AuditOutcome, AuditRecord

_IDENTIFIER = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
_MAX_PREFIX_LENGTH = 48
_MAX_SNAPSHOT_BYTES = 65_536
_MAX_METADATA_BYTES = {"actor": 256, "action": 128, "resource": 512}
_FORBIDDEN_KEY_PARTS = (
    "secret",
    "credential",
    "password",
    "verifier",
    "session",
    "csrf",
    "token",
    "cookie",
    "authorization",
    "header",
    "api_key",
    "apikey",
    "client_secret",
    "clientsecret",
    "private_key",
    "privatekey",
    "access_key",
    "accesskey",
    "bearer",
)
_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?:\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+"
    r"|\b(?:password|secret|session[\s_-]*token|csrf|api[\s_-]*key|"
    r"authorization|cookie)\b"
    r"|\b(?:access_token|refresh_token|token)\s*[:=]\s*['\"]?"
    r"[A-Za-z0-9._~+/=-]+"
    r"|(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r"\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"
    r"|(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-]))",
    re.IGNORECASE,
)
_AUDIT_CONSTRAINTS = {
    "audit_event_id_pkey": ("p", "PRIMARY KEY (id)"),
    "audit_event_outcome_check": (
        "c",
        "CHECK (outcome = 'allowed' OR outcome = 'denied')",
    ),
    "audit_event_timestamp_finite_check": (
        "c",
        "CHECK (occurred_at > '-Infinity'::double precision "
        "AND occurred_at < 'Infinity'::double precision)",
    ),
    "audit_event_metadata_safe_check": (
        "c",
        "CHECK ("
        "octet_length(actor) <= 256 AND actor ~ '[^[:space:]]' "
        "AND actor !~ '[[:cntrl:]]' AND position(chr(8232) IN actor) = 0 "
        "AND position(chr(8233) IN actor) = 0 AND "
        "octet_length(action) <= 128 AND action ~ '[^[:space:]]' "
        "AND action !~ '[[:cntrl:]]' AND position(chr(8232) IN action) = 0 "
        "AND position(chr(8233) IN action) = 0 AND "
        "octet_length(resource) <= 512 AND resource ~ '[^[:space:]]' "
        "AND resource !~ '[[:cntrl:]]' AND position(chr(8232) IN resource) = 0 "
        "AND position(chr(8233) IN resource) = 0)",
    ),
}
_AUDIT_COLUMNS = {
    "id": ("bigint", True),
    "actor": ("text", True),
    "action": ("text", True),
    "resource": ("text", True),
    "outcome": ("text", True),
    "occurred_at": ("double precision", True),
    "before_json": ("text", False),
    "after_json": ("text", False),
}
_AUDIT_GUARD_FUNCTION_BODIES = {
    "row": ("BEGIN RAISE EXCEPTION 'audit rows are immutable' USING ERRCODE = '23514'; END;"),
    "truncate": (
        "BEGIN RAISE EXCEPTION 'audit table is append-only' USING ERRCODE = '23514'; END;"
    ),
}


class _Cursor(Protocol):
    def execute(self, sql: Any, params: tuple[object, ...] = ()) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass(frozen=True)
class StoredAuditEvent:
    """One persisted audit record together with its database sequence id."""

    sequence_id: int
    record: AuditRecord


def _identifier(value: str, name: str, max_length: int = 63) -> str:
    if not isinstance(value, str) or len(value) > max_length or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a safe PostgreSQL identifier")
    return value


def _qualified(schema: str, name: str) -> str:
    return f'"{schema}"."{name}"'


def _normalize_constraint_definition(definition: str) -> str:
    parts = re.split(r"('(?:''|[^'])*')", definition)
    normalized_parts = []
    for part in parts:
        if part.startswith("'") and part.endswith("'"):
            normalized_parts.append(part)
            continue
        part = re.sub(
            r"position\(chr\((8232|8233)\)\s+IN\s+(actor|action|resource)\)",
            r'"position"(\2, chr(\1))',
            part,
            flags=re.I,
        )
        part = part.replace('"position"', "position")
        part = re.sub(r"::(?:double precision|text)\b", "", part, flags=re.I)
        normalized_parts.append(re.sub(r"[\s()]", "", part).casefold())
    return "".join(normalized_parts)


def _normalize_function_source(source: str) -> str:
    return re.sub(r"\s+", " ", source).strip()


def _validate_schema_objects(
    cursor: _Cursor,
    *,
    schema: str,
    table: str,
    sequence: str,
    row_guard: str,
    truncate_guard: str,
    owner: str,
    require_complete: bool,
) -> set[str]:
    cursor.execute(
        "SELECT c.relname, c.relkind, pg_catalog.pg_get_userbyid(c.relowner) "
        "FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s ORDER BY c.relname",
        (schema,),
    )
    relations = {
        str(name): (str(kind), str(object_owner)) for name, kind, object_owner in cursor.fetchall()
    }
    expected_relations = {
        table: "r",
        sequence: "S",
        "audit_event_id_pkey": "i",
    }
    if any(
        name not in expected_relations or kind != expected_relations[name] or object_owner != owner
        for name, (kind, object_owner) in relations.items()
    ):
        raise RuntimeError("audit schema contains an unexpected or incompatible relation")
    if require_complete and set(relations) != set(expected_relations):
        raise RuntimeError("audit schema is missing a required relation")

    cursor.execute(
        "SELECT c.relname, c.oid, t.oid FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_catalog.pg_type t ON t.typrelid = c.oid "
        "WHERE n.nspname = %s AND c.relname IN (%s, %s)",
        (schema, table, sequence),
    )
    relation_types = {
        str(name): (int(relation_oid), int(row_type_oid))
        for name, relation_oid, row_type_oid in cursor.fetchall()
    }

    cursor.execute(
        "SELECT t.typname, t.typtype, t.typrelid, t.typelem, "
        "pg_catalog.pg_get_userbyid(t.typowner) "
        "FROM pg_catalog.pg_type t "
        "JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname = %s ORDER BY t.typname",
        (schema,),
    )
    types = {
        str(name): (str(kind), int(relation_oid), int(element_oid), str(type_owner))
        for name, kind, relation_oid, element_oid, type_owner in cursor.fetchall()
    }
    expected_types: dict[str, tuple[str, int, int, str]] = {}
    for relation_name, (relation_oid, row_type_oid) in relation_types.items():
        expected_types[relation_name] = ("c", relation_oid, 0, owner)
        if relation_name == table:
            expected_types[f"_{relation_name}"] = ("b", 0, row_type_oid, owner)
    if any(
        name not in expected_types or value != expected_types[name] for name, value in types.items()
    ):
        raise RuntimeError("audit schema contains an unexpected or incompatible type")
    if require_complete and types != expected_types:
        raise RuntimeError("audit schema is missing a required type")

    function_expectations = {
        row_guard: _AUDIT_GUARD_FUNCTION_BODIES["row"],
        truncate_guard: _AUDIT_GUARD_FUNCTION_BODIES["truncate"],
    }
    cursor.execute(
        "SELECT p.proname, p.prokind, p.prosecdef, "
        "pg_catalog.pg_get_userbyid(p.proowner), l.lanname, "
        "pg_catalog.format_type(p.prorettype, NULL), p.pronargs, p.proconfig, p.prosrc "
        "FROM pg_catalog.pg_proc p "
        "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
        "JOIN pg_catalog.pg_language l ON l.oid = p.prolang "
        "WHERE n.nspname = %s ORDER BY p.proname",
        (schema,),
    )
    functions: set[str] = set()
    function_rows = cursor.fetchall()
    for (
        name,
        kind,
        security_definer,
        function_owner,
        language,
        return_type,
        nargs,
        config,
        source,
    ) in function_rows:
        function_name = str(name)
        expected_source = function_expectations.get(function_name)
        actual_config = None if config is None else tuple(config)
        if (
            expected_source is None
            or function_name in functions
            or str(kind) != "f"
            or bool(security_definer)
            or str(function_owner) != owner
            or str(language) != "plpgsql"
            or str(return_type) != "trigger"
            or int(nargs) != 0
            or actual_config != ("search_path=pg_catalog",)
            or _normalize_function_source(str(source))
            != _normalize_function_source(expected_source)
        ):
            raise RuntimeError("audit schema contains an unexpected or incompatible function")
        functions.add(function_name)
    if require_complete and functions != set(function_expectations):
        raise RuntimeError("audit schema is missing a required function")
    return functions


def _contains_forbidden_key(key: str) -> bool:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", separated).strip("_").casefold()
    compact = normalized.replace("_", "")
    return any(
        part in normalized or part.replace("_", "") in compact for part in _FORBIDDEN_KEY_PARTS
    )


def _validate_json_value(value: object, ancestors: set[int]) -> None:
    if type(value) is str:
        if _SENSITIVE_VALUE_PATTERN.search(value):
            raise ValueError("audit snapshots must not contain credential values")
        return
    if value is None or type(value) in (bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("audit snapshots must not contain non-finite numbers")
        return
    if type(value) not in (dict, list):
        raise TypeError("audit snapshots must contain only JSON values")

    identity = id(value)
    if identity in ancestors:
        raise ValueError("audit snapshots must not contain circular references")
    ancestors.add(identity)
    try:
        if type(value) is dict:
            for key, nested in value.items():
                if type(key) is not str:
                    raise TypeError("audit snapshot JSON object keys must be strings")
                if _contains_forbidden_key(key):
                    raise ValueError("audit snapshots must not contain credential fields")
                _validate_json_value(nested, ancestors)
        elif type(value) is list:
            for nested in value:
                _validate_json_value(nested, ancestors)
    finally:
        ancestors.remove(identity)


def _serialize_snapshot(value: object | None) -> str | None:
    if value is None:
        return None
    _validate_json_value(value, set())
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    try:
        encoded = serialized.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("audit snapshots must be valid UTF-8 JSON") from exc
    if len(encoded) > _MAX_SNAPSHOT_BYTES:
        raise ValueError("audit snapshots must not exceed 65536 UTF-8 bytes")
    return serialized


def _validate_event(record: AuditRecord) -> tuple[float, str | None, str | None]:
    if not isinstance(record, AuditRecord):
        raise TypeError("event must be an AuditRecord")
    for field_name in ("actor", "action", "resource"):
        field_value = getattr(record, field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            raise ValueError(f"audit {field_name} must be non-empty text")
        try:
            encoded = field_value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(f"audit {field_name} must be valid UTF-8 text") from exc
        if len(encoded) > _MAX_METADATA_BYTES[field_name]:
            raise ValueError(
                f"audit {field_name} must not exceed {_MAX_METADATA_BYTES[field_name]} UTF-8 bytes"
            )
        forbidden_categories = {"Cc", "Cf", "Cs", "Zl", "Zp"}
        if any(
            unicodedata.category(character) in forbidden_categories for character in field_value
        ):
            raise ValueError(f"audit {field_name} must not contain control or format characters")
    if type(record.outcome) is not AuditOutcome:
        raise TypeError("audit outcome must be an AuditOutcome")
    if isinstance(record.at, bool) or not isinstance(record.at, (int, float)):
        raise TypeError("audit timestamp must be a finite number")
    timestamp = float(record.at)
    if not math.isfinite(timestamp):
        raise ValueError("audit timestamp must be a finite number")
    return (
        timestamp,
        _serialize_snapshot(record.before_value),
        _serialize_snapshot(record.after_value),
    )


def _event_from_row(row: tuple[Any, ...]) -> StoredAuditEvent:
    sequence_id, actor, action, resource, outcome, timestamp, before_json, after_json = row
    return StoredAuditEvent(
        sequence_id=int(sequence_id),
        record=AuditRecord(
            actor=str(actor),
            action=str(action),
            resource=str(resource),
            outcome=AuditOutcome(str(outcome)),
            at=float(timestamp),
            before_value=None if before_json is None else json.loads(str(before_json)),
            after_value=None if after_json is None else json.loads(str(after_json)),
        ),
    )


class PostgresAuditStore:
    """Append-only audit repository on a caller-owned PostgreSQL connection.

    Use a dedicated, exclusive connection. On any error this store rolls back
    the entire active transaction, even when ``commit=False``. That option
    defers a successful commit only; it does not create savepoint isolation.
    The connection is never opened, closed, or reconfigured here, and this
    repository has no update or delete operation. See ADR-0024 and REQ-S-4.
    """

    def __init__(
        self,
        connection: _Connection,
        *,
        schema: str = "console_audit",
        prefix: str = "console_audit",
    ) -> None:
        """Wrap a connection and a schema-qualified set of audit objects."""
        _identifier(schema, "schema")
        if schema == "public":
            raise ValueError("audit schema must not be public")
        _identifier(prefix, "prefix", _MAX_PREFIX_LENGTH)
        self._connection = connection
        self.schema = schema
        self.prefix = prefix
        self.table = f"{prefix}_events"
        self.sequence = f"{prefix}_event_id_seq"
        digest = hashlib.sha256(f"{schema}.{prefix}".encode("ascii")).hexdigest()[:16]
        self._row_guard = f"as_audit_row_guard_{digest}"
        self._truncate_guard = f"as_audit_truncate_guard_{digest}"

    @property
    def qualified_table(self) -> str:
        """The fully qualified, safely quoted audit table name."""
        return _qualified(self.schema, self.table)

    @property
    def qualified_sequence(self) -> str:
        """The fully qualified, safely quoted audit sequence name."""
        return _qualified(self.schema, self.sequence)

    def ensure_schema(self, runtime_role: str) -> None:
        """Create the audit objects and least-privilege grants as their owner.

        This is migration/owner work, not an application-runtime operation;
        it never creates or drops a role or changes search_path.
        """
        try:
            role = _identifier(runtime_role, "runtime_role")
            from psycopg import sql

            cursor = self._connection.cursor()
            cursor.execute(
                "SELECT rolsuper, rolcreaterole FROM pg_catalog.pg_roles WHERE rolname = %s",
                (role,),
            )
            role_row = cursor.fetchone()
            if role_row is None:
                raise ValueError("runtime_role must already exist")
            if bool(role_row[0]):
                raise ValueError("runtime_role must not be a superuser")
            if bool(role_row[1]):
                raise ValueError("runtime_role must not have CREATEROLE")
            cursor.execute("SELECT current_user")
            current_user_row = cursor.fetchone()
            if current_user_row is None:
                raise RuntimeError("could not determine the current database role")
            owner = str(current_user_row[0])
            if role == owner:
                raise ValueError("runtime_role must not own the audit objects")

            cursor.execute(
                "WITH RECURSIVE member_roles(role_oid) AS ("
                "SELECT m.roleid FROM pg_catalog.pg_auth_members m "
                "JOIN pg_catalog.pg_roles runtime ON runtime.oid = m.member "
                "WHERE runtime.rolname = %s "
                "UNION "
                "SELECT m.roleid FROM pg_catalog.pg_auth_members m "
                "JOIN member_roles granted_role ON m.member = granted_role.role_oid) "
                "SELECT EXISTS (SELECT 1 FROM member_roles)",
                (role,),
            )
            membership_row = cursor.fetchone()
            if membership_row is None:
                raise RuntimeError("could not determine runtime role memberships")
            if bool(membership_row[0]):
                raise ValueError("runtime_role must not be a member of another database role")

            cursor.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema))
            )
            cursor.execute(
                "SELECT pg_catalog.pg_get_userbyid(n.nspowner) "
                "FROM pg_catalog.pg_namespace n WHERE n.nspname = %s",
                (self.schema,),
            )
            schema_owner_row = cursor.fetchone()
            if schema_owner_row is None:
                raise RuntimeError("audit schema was not created")
            if str(schema_owner_row[0]) != owner:
                raise ValueError("audit schema must be owned by the current database role")

            existing_functions = _validate_schema_objects(
                cursor,
                schema=self.schema,
                table=self.table,
                sequence=self.sequence,
                row_guard=self._row_guard,
                truncate_guard=self._truncate_guard,
                owner=owner,
                require_complete=False,
            )

            table = self.qualified_table
            sequence = self.qualified_sequence
            regclass_input = ".".join(
                part if part == part.lower() else f'"{part}"'
                for part in (self.schema, self.sequence)
            )
            row_guard = _qualified(self.schema, self._row_guard)
            truncate_guard = _qualified(self.schema, self._truncate_guard)
            cursor.execute(
                "SELECT c.relkind FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s",
                (self.schema, self.table),
            )
            existing_table_row = cursor.fetchone()
            if existing_table_row is not None and str(existing_table_row[0]) != "r":
                raise RuntimeError("audit table name is occupied by an incompatible object")
            table_existed = existing_table_row is not None

            cursor.execute(f"CREATE SEQUENCE IF NOT EXISTS {sequence}")
            cursor.execute(
                "SELECT pg_catalog.format_type(s.seqtypid, NULL), s.seqstart, s.seqmin, "
                "s.seqincrement, s.seqmax, s.seqcycle "
                "FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_catalog.pg_sequence s ON s.seqrelid = c.oid "
                "WHERE n.nspname = %s AND c.relname = %s AND c.relkind = 'S'",
                (self.schema, self.sequence),
            )
            sequence_settings = cursor.fetchone()
            if (
                sequence_settings is None
                or str(sequence_settings[0]) != "bigint"
                or int(sequence_settings[1]) != 1
                or int(sequence_settings[2]) != 1
                or int(sequence_settings[3]) != 1
                or int(sequence_settings[4]) != 9_223_372_036_854_775_807
                or bool(sequence_settings[5])
            ):
                raise RuntimeError("audit id sequence settings are incompatible")
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {table} ("
                f"id BIGINT CONSTRAINT audit_event_id_pkey PRIMARY KEY DEFAULT nextval("
                f"'{sequence}'::regclass), "
                "actor TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL, "
                "outcome TEXT NOT NULL, occurred_at DOUBLE PRECISION NOT NULL, "
                "before_json TEXT, after_json TEXT, "
                f"CONSTRAINT audit_event_outcome_check "
                f"{_AUDIT_CONSTRAINTS['audit_event_outcome_check'][1]}, "
                f"CONSTRAINT audit_event_timestamp_finite_check "
                f"{_AUDIT_CONSTRAINTS['audit_event_timestamp_finite_check'][1]}, "
                f"CONSTRAINT audit_event_metadata_safe_check "
                f"{_AUDIT_CONSTRAINTS['audit_event_metadata_safe_check'][1]})"
            )
            if not table_existed:
                cursor.execute(f"ALTER SEQUENCE {sequence} OWNED BY {table}.id")

            cursor.execute(
                "SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), "
                "a.attnotnull FROM pg_catalog.pg_attribute a "
                "JOIN pg_catalog.pg_class c ON c.oid = a.attrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s "
                "AND a.attnum > 0 AND NOT a.attisdropped",
                (self.schema, self.table),
            )
            columns = {
                str(name): (str(data_type), bool(not_null))
                for name, data_type, not_null in cursor.fetchall()
            }
            if columns != _AUDIT_COLUMNS:
                raise RuntimeError("audit table has incompatible columns")

            cursor.execute(
                "SELECT pg_catalog.pg_get_expr(d.adbin, d.adrelid), "
                "pg_catalog.pg_get_serial_sequence(%s, 'id') "
                "FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attname = 'id' "
                "LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum "
                "WHERE n.nspname = %s AND c.relname = %s",
                (table, self.schema, self.table),
            )
            default_row = cursor.fetchone()
            expected_default = f"nextval('{regclass_input}'::regclass)"
            if default_row is None or str(default_row[0]) != expected_default:
                actual_default = None if default_row is None else default_row[0]
                raise RuntimeError(
                    f"audit id default does not target the required sequence: {actual_default!r}"
                )
            cursor.execute(
                "SELECT pg_catalog.to_regclass(%s) = pg_catalog.to_regclass(%s), "
                "c.relkind, pg_catalog.format_type(s.seqtypid, NULL) "
                "FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "LEFT JOIN pg_catalog.pg_sequence s ON s.seqrelid = c.oid "
                "WHERE n.nspname = %s AND c.relname = %s",
                (default_row[1], sequence, self.schema, self.sequence),
            )
            sequence_row = cursor.fetchone()
            if (
                sequence_row is None
                or sequence_row[0] is not True
                or str(sequence_row[1]) != "S"
                or str(sequence_row[2]) != "bigint"
            ):
                raise RuntimeError("audit id sequence ownership is incompatible")

            cursor.execute(
                "SELECT c.conname, c.contype, pg_catalog.pg_get_constraintdef(c.oid, true), "
                "c.convalidated FROM pg_catalog.pg_constraint c "
                "JOIN pg_catalog.pg_class t ON t.oid = c.conrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = %s AND t.relname = %s",
                (self.schema, self.table),
            )
            constraints = {
                str(name): (str(kind), str(definition), bool(validated))
                for name, kind, definition, validated in cursor.fetchall()
            }
            for constraint_name, (expected_kind, expected_definition) in _AUDIT_CONSTRAINTS.items():
                existing = constraints.get(constraint_name)
                if existing is not None and (
                    existing[0] != expected_kind
                    or _normalize_constraint_definition(existing[1])
                    != _normalize_constraint_definition(expected_definition)
                ):
                    raise RuntimeError(f"audit constraint {constraint_name} is incompatible")
                if existing is None:
                    try:
                        cursor.execute(
                            f"ALTER TABLE {table} ADD CONSTRAINT {constraint_name} "
                            f"{expected_definition}"
                        )
                    except Exception as exc:
                        raise RuntimeError(
                            f"existing audit rows violate required constraint {constraint_name}"
                        ) from exc
                elif not existing[2]:
                    try:
                        cursor.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint_name}")
                    except Exception as exc:
                        raise RuntimeError(
                            f"existing audit rows violate required constraint {constraint_name}"
                        ) from exc

            cursor.execute(
                "SELECT c.conname, c.contype, pg_catalog.pg_get_constraintdef(c.oid, true), "
                "c.convalidated FROM pg_catalog.pg_constraint c "
                "JOIN pg_catalog.pg_class t ON t.oid = c.conrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = %s AND t.relname = %s",
                (self.schema, self.table),
            )
            verified_constraints = {
                str(name): (str(kind), str(definition), bool(validated))
                for name, kind, definition, validated in cursor.fetchall()
            }
            if set(verified_constraints) != set(_AUDIT_CONSTRAINTS):
                raise RuntimeError("audit table contains an unexpected constraint")
            for constraint_name, (expected_kind, expected_definition) in _AUDIT_CONSTRAINTS.items():
                kind, definition, validated = verified_constraints[constraint_name]
                if kind != expected_kind or _normalize_constraint_definition(
                    definition
                ) != _normalize_constraint_definition(expected_definition):
                    raise RuntimeError(f"audit constraint {constraint_name} is incompatible")
                if not validated:
                    raise RuntimeError(f"audit constraint {constraint_name} is not validated")

            cursor.execute(
                "SELECT t.tgname, t.tgtype, t.tgenabled, fn_ns.nspname, fn.proname "
                "FROM pg_catalog.pg_trigger t "
                "JOIN pg_catalog.pg_proc fn ON fn.oid = t.tgfoid "
                "JOIN pg_catalog.pg_namespace fn_ns ON fn_ns.oid = fn.pronamespace "
                "WHERE t.tgrelid = pg_catalog.to_regclass(%s) AND NOT t.tgisinternal",
                (table,),
            )
            expected_triggers = {
                "audit_row_immutable": (27, "O", self.schema, self._row_guard),
                "audit_table_immutable": (34, "O", self.schema, self._truncate_guard),
            }
            existing_triggers = {
                str(name): (
                    int(trigger_type),
                    str(enabled),
                    str(function_schema),
                    str(function_name),
                )
                for name, trigger_type, enabled, function_schema, function_name in cursor.fetchall()
            }
            if any(
                name not in expected_triggers or definition != expected_triggers[name]
                for name, definition in existing_triggers.items()
            ):
                raise RuntimeError("audit table has an unexpected or incompatible trigger")

            if self._row_guard not in existing_functions:
                cursor.execute(
                    f"CREATE FUNCTION {row_guard}() RETURNS trigger "
                    "LANGUAGE plpgsql SET search_path = pg_catalog AS $audit_guard$ "
                    "BEGIN RAISE EXCEPTION 'audit rows are immutable' USING ERRCODE = '23514'; "
                    "END; $audit_guard$"
                )
            if self._truncate_guard not in existing_functions:
                cursor.execute(
                    f"CREATE FUNCTION {truncate_guard}() RETURNS trigger "
                    "LANGUAGE plpgsql SET search_path = pg_catalog AS $audit_guard$ "
                    "BEGIN RAISE EXCEPTION 'audit table is append-only' USING ERRCODE = '23514'; "
                    "END; $audit_guard$"
                )
            if "audit_row_immutable" not in existing_triggers:
                cursor.execute(
                    f"CREATE TRIGGER audit_row_immutable BEFORE UPDATE OR DELETE ON {table} "
                    f"FOR EACH ROW EXECUTE FUNCTION {row_guard}()"
                )
            if "audit_table_immutable" not in existing_triggers:
                cursor.execute(
                    f"CREATE TRIGGER audit_table_immutable BEFORE TRUNCATE ON {table} "
                    f"FOR EACH STATEMENT EXECUTE FUNCTION {truncate_guard}()"
                )
            _validate_schema_objects(
                cursor,
                schema=self.schema,
                table=self.table,
                sequence=self.sequence,
                row_guard=self._row_guard,
                truncate_guard=self._truncate_guard,
                owner=owner,
                require_complete=True,
            )
            cursor.execute(
                sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA {} FROM PUBLIC").format(
                    sql.Identifier(self.schema)
                )
            )
            cursor.execute(
                sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA {} FROM {}").format(
                    sql.Identifier(self.schema), sql.Identifier(role)
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(self.schema), sql.Identifier(role)
                )
            )
            cursor.execute(f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM PUBLIC")
            cursor.execute(
                sql.SQL("REVOKE ALL PRIVILEGES ON TABLE {} FROM {}").format(
                    sql.SQL(table), sql.Identifier(role)
                )
            )
            cursor.execute(
                sql.SQL("GRANT SELECT, INSERT ON TABLE {} TO {}").format(
                    sql.SQL(table), sql.Identifier(role)
                )
            )
            cursor.execute(f"REVOKE ALL PRIVILEGES ON SEQUENCE {sequence} FROM PUBLIC")
            cursor.execute(
                sql.SQL("REVOKE ALL PRIVILEGES ON SEQUENCE {} FROM {}").format(
                    sql.SQL(sequence), sql.Identifier(role)
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE, SELECT ON SEQUENCE {} TO {}").format(
                    sql.SQL(sequence), sql.Identifier(role)
                )
            )
            cursor.execute(f"REVOKE ALL ON FUNCTION {row_guard}() FROM PUBLIC")
            cursor.execute(
                sql.SQL("REVOKE ALL ON FUNCTION {}() FROM {}").format(
                    sql.SQL(row_guard), sql.Identifier(role)
                )
            )
            cursor.execute(f"REVOKE ALL ON FUNCTION {truncate_guard}() FROM PUBLIC")
            cursor.execute(
                sql.SQL("REVOKE ALL ON FUNCTION {}() FROM {}").format(
                    sql.SQL(truncate_guard), sql.Identifier(role)
                )
            )
            cursor.execute(
                "SELECT pg_catalog.pg_get_userbyid(c.relowner), "
                "pg_catalog.has_table_privilege(%s, c.oid, 'SELECT'), "
                "pg_catalog.has_table_privilege(%s, c.oid, 'INSERT'), "
                "pg_catalog.has_table_privilege(%s, c.oid, 'UPDATE'), "
                "pg_catalog.has_table_privilege(%s, c.oid, 'DELETE'), "
                "pg_catalog.has_table_privilege(%s, c.oid, 'TRUNCATE') "
                "FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s AND c.relkind = 'r'",
                (role, role, role, role, role, self.schema, self.table),
            )
            privileges = cursor.fetchone()
            if privileges is None:
                raise RuntimeError("audit table was not created")
            object_owner, can_select, can_insert, can_update, can_delete, can_truncate = privileges
            if str(object_owner) == role:
                raise ValueError("runtime_role must not own the audit table")
            if not can_select or not can_insert:
                raise RuntimeError("runtime_role must have effective SELECT and INSERT privileges")
            if can_update or can_delete or can_truncate:
                raise RuntimeError("runtime_role has effective audit mutation privileges")

            cursor.execute(
                "SELECT pg_catalog.has_schema_privilege(%s, %s, 'CREATE'), "
                "pg_catalog.pg_get_userbyid(s.relowner), "
                "pg_catalog.has_sequence_privilege(%s, s.oid, 'USAGE'), "
                "pg_catalog.has_sequence_privilege(%s, s.oid, 'SELECT'), "
                "pg_catalog.has_sequence_privilege(%s, s.oid, 'UPDATE') "
                "FROM pg_catalog.pg_class s "
                "JOIN pg_catalog.pg_namespace n ON n.oid = s.relnamespace "
                "WHERE n.nspname = %s AND s.relname = %s AND s.relkind = 'S'",
                (role, self.schema, role, role, role, self.schema, self.sequence),
            )
            sequence_privileges = cursor.fetchone()
            if sequence_privileges is None:
                raise RuntimeError("audit sequence was not created")
            (
                can_create_schema_objects,
                sequence_owner,
                can_use_sequence,
                can_select_sequence,
                can_update_sequence,
            ) = sequence_privileges
            if can_create_schema_objects:
                raise RuntimeError("runtime_role has effective audit schema CREATE privileges")
            if str(sequence_owner) == role:
                raise ValueError("runtime_role must not own the audit sequence")
            if not can_use_sequence or not can_select_sequence:
                raise RuntimeError(
                    "runtime_role must have effective sequence USAGE and SELECT privileges"
                )
            if can_update_sequence:
                raise RuntimeError("runtime_role has effective audit sequence UPDATE privileges")
            self._connection.commit()
        except BaseException:
            with suppress(BaseException):
                self._connection.rollback()
            raise

    def append(self, event: AuditRecord, *, commit: bool = True) -> StoredAuditEvent:
        """Append a validated event, committing success unless caller-owned."""
        try:
            timestamp, before_json, after_json = _validate_event(event)
            cursor = self._connection.cursor()
            cursor.execute(
                f"INSERT INTO {self.qualified_table} "
                "(actor, action, resource, outcome, occurred_at, before_json, after_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id, actor, action, resource, outcome, occurred_at, "
                "before_json, after_json",
                (
                    event.actor,
                    event.action,
                    event.resource,
                    event.outcome.value,
                    timestamp,
                    before_json,
                    after_json,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("appending an audit event returned no persisted event")
            stored = _event_from_row(row)
            if commit:
                self._connection.commit()
            return stored
        except BaseException:
            with suppress(BaseException):
                self._connection.rollback()
            raise

    def list_events(self) -> tuple[StoredAuditEvent, ...]:
        """Read all events in immutable sequence order without committing."""
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT id, actor, action, resource, outcome, occurred_at, "
                f"before_json, after_json FROM {self.qualified_table} ORDER BY id ASC"
            )
            return tuple(_event_from_row(row) for row in cursor.fetchall())
        except BaseException:
            with suppress(BaseException):
                self._connection.rollback()
            raise
