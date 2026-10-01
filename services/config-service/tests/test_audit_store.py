"""Unit tests for audit snapshot serialization and transaction policy. REQ-S-4."""

from __future__ import annotations

from typing import Any

import pytest

from as_config_service.audit_store import (
    PostgresAuditStore,
    _normalize_constraint_definition,
    _serialize_snapshot,
)
from as_console.access import AuditOutcome, AuditRecord

pytestmark = pytest.mark.unit


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.row: tuple[object, ...] | None = None
        self.rows: list[tuple[Any, ...]] = []

    def execute(self, sql: Any, params: tuple[object, ...] = ()) -> None:
        statement = str(sql)
        self.connection.statements.append((statement, params))
        if "RETURNING id," in statement:
            self.row = (self.connection.next_id, *params)
            self.connection.persisted_rows.append(self.row)
            self.connection.next_id += 1
        if self.connection.fail_execute:
            raise RuntimeError("database mutation failed")

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.row

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.connection.persisted_rows


class _Connection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.next_id = 1
        self.persisted_rows: list[tuple[Any, ...]] = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_execute = False

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _record(**overrides: object) -> AuditRecord:
    values: dict[str, object] = {
        "actor": "ops-alice",
        "action": "rule.update",
        "resource": "rule:international",
        "outcome": AuditOutcome.ALLOWED,
        "at": 1_700_000_000.25,
    }
    values.update(overrides)
    return AuditRecord(**values)  # type: ignore[arg-type]


def test_snapshot_json_is_canonical_and_deterministic() -> None:
    assert _serialize_snapshot({"z": [2, "x"], "a": {"enabled": True}}) == (
        '{"a":{"enabled":true},"z":[2,"x"]}'
    )
    assert _serialize_snapshot({"a": 1, "b": 2}) == _serialize_snapshot({"b": 2, "a": 1})


def test_absent_snapshots_serialize_to_sql_null() -> None:
    assert _serialize_snapshot(None) is None


def test_constraint_normalization_preserves_string_literal_case() -> None:
    expected = "CHECK (outcome = 'allowed' OR outcome = 'denied')"

    assert _normalize_constraint_definition(
        "check ((OUTCOME = 'allowed') or (outcome = 'denied'))"
    ) == _normalize_constraint_definition(expected)
    assert _normalize_constraint_definition(
        "CHECK (outcome = 'ALLOWED' OR outcome = 'DENIED')"
    ) != _normalize_constraint_definition(expected)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {"nested": [float("-inf")]}])
def test_non_finite_snapshot_numbers_are_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        _serialize_snapshot(value)


@pytest.mark.parametrize("value", [object(), {1: "not a JSON object key"}, {"tuple": (1, 2)}])
def test_non_json_snapshot_values_are_rejected(value: object) -> None:
    with pytest.raises(TypeError, match="JSON"):
        _serialize_snapshot(value)


def test_oversized_snapshot_is_rejected_by_utf8_byte_length() -> None:
    with pytest.raises(ValueError, match="65536"):
        _serialize_snapshot({"value": "é" * 32_768})


@pytest.mark.parametrize(
    "key",
    [
        "PasswordHash",
        "password_verifier",
        "secretValue",
        "credential_hint",
        "active_session_id",
        "csrfToken",
        "access_token_value",
        "cookieJar",
        "authorizationHeader",
        "request_headers",
        "apiKey",
        "api-key",
        "clientSecret",
        "private_key",
        "accessKey",
        "bearerToken",
    ],
)
def test_credential_fields_are_rejected_recursively_and_case_insensitively(key: str) -> None:
    with pytest.raises(ValueError, match="credential"):
        _serialize_snapshot({"nested": [{key: "sensitive"}]})


@pytest.mark.parametrize(
    "value",
    [
        "Bearer abcdefghijklmnop",
        "Basic dXNlcjpwYXNzd29yZA",
        "password=hunter2",
        "token=abc123",
        "access_token=access123",
        "refresh_token=refresh123",
        "secret: value",
        "session token: abc123",
        "csrf",
        "api_key=abc123",
        "authorization: Bearer abc123",
        "cookie=sessionid",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturevalue123",
        "a" * 43,
    ],
)
def test_credential_looking_values_are_rejected_recursively(value: str) -> None:
    with pytest.raises(ValueError, match="credential"):
        _serialize_snapshot({"nested": [{"note": value}]})


def test_plain_token_word_without_assignment_is_not_rejected() -> None:
    assert _serialize_snapshot({"note": "the token is an opaque identifier"}) == (
        '{"note":"the token is an opaque identifier"}'
    )


def test_store_validates_names_and_has_no_mutation_api() -> None:
    connection = _Connection()
    for name in ('bad"schema', "schema.with.dot", "schema;drop"):
        with pytest.raises(ValueError, match="schema"):
            PostgresAuditStore(connection, schema=name)
    with pytest.raises(ValueError, match="must not be public"):
        PostgresAuditStore(connection, schema="public")
    for prefix in ("bad-prefix", "x" * 49, "events;drop"):
        with pytest.raises(ValueError, match="prefix"):
            PostgresAuditStore(connection, prefix=prefix)
    store = PostgresAuditStore(connection)
    with pytest.raises(ValueError, match="runtime_role"):
        store.ensure_schema("bad role")
    assert not hasattr(store, "update")
    assert not hasattr(store, "delete")
    assert connection.statements == []


def test_append_persists_snapshots_but_never_detail_and_commits_by_default() -> None:
    connection = _Connection()
    store = PostgresAuditStore(connection)
    event = _record(
        detail="not persisted",
        before_value={"enabled": False},
        after_value={"enabled": True},
    )

    stored = store.append(event)

    assert stored.sequence_id == 1
    statement, params = connection.statements[0]
    assert '"console_audit"."console_audit_events"' in statement
    assert params == (
        "ops-alice",
        "rule.update",
        "rule:international",
        "allowed",
        1_700_000_000.25,
        '{"enabled":false}',
        '{"enabled":true}',
    )
    assert "detail" not in statement
    assert connection.commits == 1


def test_append_returns_detached_canonical_persisted_record() -> None:
    connection = _Connection()
    store = PostgresAuditStore(connection)
    before = {"nested": {"enabled": False}}
    after = {"nested": {"enabled": True}}
    event = _record(detail="not persisted", before_value=before, after_value=after)

    stored = store.append(event)
    before["nested"]["enabled"] = True
    after["nested"]["enabled"] = False

    assert stored.record.before_value == {"nested": {"enabled": False}}
    assert stored.record.after_value == {"nested": {"enabled": True}}
    assert stored.record.detail == ""
    assert store.list_events() == (stored,)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("actor", "é" * 129, "256 UTF-8 bytes"),
        ("action", "a" * 129, "128 UTF-8 bytes"),
        ("resource", "r" * 513, "512 UTF-8 bytes"),
        ("actor", "   ", "non-empty"),
        ("action", "bad\nvalue", "control or format"),
        ("actor", "bad\x01value", "control or format"),
        ("actor", "bad\ud800value", "valid UTF-8"),
        ("resource", "bad\u200evalue", "control or format"),
        ("resource", "bad\u2028value", "control or format"),
        ("resource", "bad\u2029value", "control or format"),
    ],
)
def test_event_metadata_is_bounded_and_safe(field: str, value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        PostgresAuditStore(_Connection()).append(_record(**{field: value}))


def test_append_can_join_a_caller_transaction_without_committing() -> None:
    connection = _Connection()
    store = PostgresAuditStore(connection)

    store.append(_record(), commit=False)

    assert connection.commits == 0
    assert connection.rollbacks == 0


def test_append_failure_rolls_back_even_when_commit_is_false() -> None:
    connection = _Connection()
    connection.fail_execute = True
    store = PostgresAuditStore(connection)

    with pytest.raises(RuntimeError, match="mutation failed"):
        store.append(_record(), commit=False)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_validation_failure_rolls_back_the_active_transaction() -> None:
    connection = _Connection()
    store = PostgresAuditStore(connection)

    with pytest.raises(ValueError, match="timestamp"):
        store.append(_record(at=float("nan")), commit=False)

    assert connection.rollbacks == 1
