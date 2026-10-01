"""Unit coverage for strict distribution journal snapshots. REQ-NF-10, ADR-0006."""

from __future__ import annotations

import json

import pytest

from as_config_service.distribution_store import (
    DuplicateDistributionError,
    InvalidDistributionSnapshotError,
    PostgresDistributionStore,
    StaleDistributionRevisionError,
    StoredDistribution,
    deserialize_distribution,
    serialize_distribution,
)
from as_config_service.distributor import (
    Distribution,
    DistributionPlan,
    DistributionState,
    InstanceReport,
)

pytestmark = pytest.mark.unit

_NOW = 1_700_000_000.0
_PLAN = DistributionPlan("change-1", 3, (("as-1", "as-2"), ("as-3",)))


def _stored(**overrides: object) -> StoredDistribution:
    fields: dict[str, object] = {
        "distribution": Distribution(
            plan=_PLAN,
            state=DistributionState.IN_PROGRESS,
            updated_at=_NOW,
        ),
        "revision": 1,
        "actor": "ops-alice",
        "action": "begin",
    }
    fields.update(overrides)
    return StoredDistribution(**fields)  # type: ignore[arg-type]


def _store() -> PostgresDistributionStore:
    return PostgresDistributionStore(None)  # type: ignore[arg-type]


def test_snapshot_roundtrip_is_deterministic_and_preserves_full_distribution() -> None:
    started = _stored()

    encoded = serialize_distribution(started)

    assert serialize_distribution(started) == encoded
    assert deserialize_distribution(encoded) == started
    assert encoded == (
        '{"action":"begin","actor":"ops-alice","distribution":'
        '{"completed_batches":0,"plan":{"batches":[["as-1","as-2"],["as-3"]],'
        '"change_id":"change-1","version":3},"reports":[],"rollback_reason":null,'
        '"rolled_back_to":null,"state":"in_progress","updated_at":1700000000.0},'
        '"revision":1,"schema_version":1}'
    )


@pytest.mark.parametrize(
    "encoded",
    [
        "not-json",
        '{"schema_version":1,"schema_version":1,"revision":1,"actor":"ops",'
        '"action":"begin","distribution":{}}',
        '{"schema_version":true,"revision":1,"actor":"ops","action":"begin","distribution":{}}',
        '{"schema_version":1,"revision":1,"actor":"ops","action":"begin",'
        '"distribution":{},"extra":1}',
        '{"schema_version":1,"revision":1,"actor":"ops","action":"begin",'
        '"distribution":{"updated_at":NaN}}',
        '{"schema_version":1,"revision":1,"actor":"ops","action":"begin",'
        '"distribution":{"updated_at":1e999}}',
    ],
)
def test_decoder_rejects_malformed_duplicate_or_nonfinite_json(encoded: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        deserialize_distribution(encoded)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("revision",), True),
        (("revision",), 0),
        (("actor",), " "),
        (("action",), "unexpected"),
        (("distribution", "state"), "pending"),
        (("distribution", "completed_batches"), True),
        (("distribution", "completed_batches"), -1),
        (
            ("distribution", "reports"),
            [{"instance_id": "as-1", "applied_version": 3, "healthy": 1}],
        ),
        (
            ("distribution", "reports"),
            [{"instance_id": "as-1", "applied_version": True, "healthy": True}],
        ),
        (("distribution", "plan", "version"), True),
        (("distribution", "plan", "version"), 0),
        (("distribution", "plan", "batches"), []),
        (("distribution", "plan", "batches"), [["as-1"], []]),
        (("distribution", "plan", "batches"), [["as-1"], ["as-1"]]),
        (("distribution", "updated_at"), None),
        (("distribution", "updated_at"), "now"),
    ],
)
def test_decoder_rejects_invalid_snapshot_fields(path: tuple[str, ...], value: object) -> None:
    payload = json.loads(serialize_distribution(_stored()))
    current = payload
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value

    with pytest.raises((TypeError, ValueError)):
        deserialize_distribution(json.dumps(payload))


@pytest.mark.parametrize(
    "unsafe_text",
    ["ops\nalice", "ops\u202ealice", "ops\ud800alice", "ops\u2028alice", "ops\u2029alice"],
)
def test_decoder_rejects_unsafe_event_metadata(unsafe_text: str) -> None:
    payload = json.loads(serialize_distribution(_stored()))
    payload["actor"] = unsafe_text

    with pytest.raises(ValueError):
        deserialize_distribution(json.dumps(payload))


@pytest.mark.parametrize(
    "plan",
    [
        DistributionPlan("change-1", True, (("as-1",),)),
        DistributionPlan("change-1", 0, (("as-1",),)),
        DistributionPlan(" ", 1, (("as-1",),)),
        DistributionPlan("change-1", 1, ()),
        DistributionPlan("change-1", 1, ((),)),
        DistributionPlan("change-1", 1, (("as-1",), ("as-1",))),
    ],
)
def test_create_rejects_invalid_or_empty_plans_before_database_access(
    plan: DistributionPlan,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        _store().create(plan, "ops-alice", _NOW)


@pytest.mark.parametrize("unsafe_text", [" ", "ops\nalice", "ops\u202ealice"])
def test_create_rejects_unsafe_actor_before_database_access(unsafe_text: str) -> None:
    with pytest.raises(ValueError):
        _store().create(_PLAN, unsafe_text, _NOW)


@pytest.mark.parametrize("result", [0, 1, "true", None])
def test_record_batch_rejects_non_bool_results_before_database_access(result: object) -> None:
    with pytest.raises(InvalidDistributionSnapshotError, match="actual bool"):
        _store().record_batch("change-1", {"as-1": result}, "ops-alice", _NOW, 1)  # type: ignore[dict-item]


def test_error_types_expose_duplicate_and_stale_revision_context() -> None:
    assert issubclass(DuplicateDistributionError, Exception)
    stale = StaleDistributionRevisionError("change-1", 2, 3)
    assert (stale.change_id, stale.expected_revision, stale.actual_revision) == ("change-1", 2, 3)


@pytest.mark.parametrize("prefix", ["", "bad-name", "9prefix", "x" * 57])
def test_store_rejects_unsafe_or_oversized_prefix(prefix: str) -> None:
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresDistributionStore(None, prefix=prefix)  # type: ignore[arg-type]


@pytest.mark.parametrize("schema", ["", "bad-name", "9schema", "x" * 64])
def test_store_rejects_unsafe_or_oversized_schema(schema: str) -> None:
    with pytest.raises(ValueError, match="schema must be a safe SQL identifier"):
        PostgresDistributionStore(None, schema=schema)  # type: ignore[arg-type]


def test_distribution_invariants_reject_duplicate_reporters_and_bad_rollback_fields() -> None:
    duplicate_reports = Distribution(
        _PLAN,
        DistributionState.IN_PROGRESS,
        reports=(
            InstanceReport("as-1", 3, True),
            InstanceReport("as-1", 3, True),
        ),
        updated_at=_NOW,
    )
    with pytest.raises(InvalidDistributionSnapshotError, match="only once"):
        _stored(distribution=duplicate_reports)

    bad_rollback = Distribution(
        _PLAN,
        DistributionState.ROLLED_BACK,
        rolled_back_to=1,
        rollback_reason="operator aborted",
        updated_at=_NOW,
    )
    with pytest.raises(InvalidDistributionSnapshotError, match="precede"):
        _stored(distribution=bad_rollback)
