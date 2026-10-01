"""Unit coverage for durable managed-rule snapshots. REQ-F-12."""

from __future__ import annotations

import pytest

from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService
from as_config_service.managed_rule_store import (
    DuplicateManagedRuleError,
    InvalidManagedRuleSnapshotError,
    ManagedRuleNotFoundError,
    PostgresManagedRuleStore,
    StaleManagedRuleRevisionError,
    StoredManagedRule,
    deserialize_managed_rule,
    serialize_managed_rule,
)

pytestmark = pytest.mark.unit

_NOW = 1_700_000_000.0


def _rule(**overrides: object) -> ManagedRule:
    fields: dict[str, object] = {
        "rule_id": "rule-1",
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


def _stored(**overrides: object) -> StoredManagedRule:
    fields: dict[str, object] = {
        "rule_id": "rule-1",
        "revision": 1,
        "rule": _rule(),
        "change_id": "change-1",
        "actor": "ops-alice",
        "created_at": _NOW,
    }
    fields.update(overrides)
    return StoredManagedRule(**fields)  # type: ignore[arg-type]


def test_live_snapshot_roundtrip_is_deterministic_and_keeps_regex_declarative() -> None:
    rule = _rule(match_mode=MatchMode.REGEX, match_value="[")

    encoded = serialize_managed_rule(rule)

    assert serialize_managed_rule(rule) == encoded
    assert deserialize_managed_rule(encoded) == rule
    assert deserialize_managed_rule(encoded).match_value == "["


def test_tombstone_snapshot_roundtrip() -> None:
    encoded = serialize_managed_rule(None)

    assert encoded == '{"rule":null,"schema_version":1}'
    assert deserialize_managed_rule(encoded) is None


@pytest.mark.parametrize(
    "encoded",
    [
        "not-json",
        '{"schema_version":2,"rule":null}',
        '{"schema_version":1,"schema_version":1,"rule":null}',
        '{"schema_version":1,"rule":null,"extra":true}',
        '{"schema_version":1,"rule":{"rule_id":"r"}}',
        '{"schema_version":true,"rule":null}',
        '{"schema_version":1,"rule":{"rule_id":"r","name":"n",'
        '"match_field":"calling","match_mode":"prefix","match_value":"x",'
        '"target_service":"translation","enabled":1,"target_detail":null}}',
        '{"schema_version":NaN,"rule":null}',
    ],
)
def test_decoder_rejects_malformed_or_non_exact_snapshots(encoded: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        deserialize_managed_rule(encoded)


@pytest.mark.parametrize(
    "fields",
    [
        {"revision": 0},
        {"revision": True},
        {"rule_id": " "},
        {"change_id": "\t"},
        {"actor": " "},
        {"created_at": float("inf")},
        {"created_at": float("nan")},
        {"rule": object()},
    ],
)
def test_stored_snapshot_validates_fields(fields: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        _stored(**fields)


def test_managed_rule_snapshot_invariant_rejects_rule_id_mismatch() -> None:
    with pytest.raises(InvalidManagedRuleSnapshotError):
        _stored(rule=_rule(rule_id="other"))


def test_error_types_expose_duplicate_missing_and_cas_context() -> None:
    assert issubclass(DuplicateManagedRuleError, Exception)
    assert issubclass(ManagedRuleNotFoundError, LookupError)
    stale = StaleManagedRuleRevisionError("rule-1", 2, 3)
    assert (stale.rule_id, stale.expected_revision, stale.actual_revision) == ("rule-1", 2, 3)


@pytest.mark.parametrize("prefix", ["", "bad-name", "9prefix", "x" * 57])
def test_store_rejects_unsafe_or_oversized_prefix(prefix: str) -> None:
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresManagedRuleStore(None, prefix=prefix)  # type: ignore[arg-type]


@pytest.mark.parametrize("schema", ["", "bad-name", "9schema", "x" * 64])
def test_store_rejects_unsafe_or_oversized_schema(schema: str) -> None:
    with pytest.raises(ValueError, match="schema must be a safe SQL identifier"):
        PostgresManagedRuleStore(None, schema=schema)  # type: ignore[arg-type]


def test_create_rejects_wrong_model_before_database_access() -> None:
    store = PostgresManagedRuleStore(None)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="ManagedRule"):
        store.create(object(), "change-1", "ops-alice", _NOW)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["change_id", "actor"])
def test_append_rejects_blank_metadata_before_database_access(field: str) -> None:
    store = PostgresManagedRuleStore(None)  # type: ignore[arg-type]
    metadata = {"change_id": "change-1", "actor": "ops-alice"}
    metadata[field] = " \t "

    with pytest.raises(ValueError, match="must not be blank"):
        store.append("rule-1", _rule(), created_at=_NOW, expected_revision=1, **metadata)
