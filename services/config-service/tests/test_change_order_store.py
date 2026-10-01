"""Unit coverage for change-order serialization and append contracts. REQ-F-14."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from as_config_service.change_order import (
    AuditEntry,
    ChangeOrder,
    ChangeState,
    ManagedRuleChange,
    ManagedRuleChangeAction,
    approve,
    begin_distribution,
    mark_applied,
    reject,
    submit,
)
from as_config_service.change_order_store import (
    DuplicateChangeOrderError,
    InvalidChangeOrderTransitionError,
    PostgresChangeOrderStore,
    StaleChangeOrderRevisionError,
    StoredChangeOrder,
    _validate_transition,
    deserialize_audit_entry,
    deserialize_order,
    serialize_audit_entry,
    serialize_order,
)
from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService
from as_platform.api.contract import ConfigBundle, RuleDTO, ToggleDTO

pytestmark = pytest.mark.unit


def _order() -> ChangeOrder:
    return ChangeOrder(
        change_id="co-1",
        state=ChangeState.DRAFT,
        bundle=ConfigBundle(
            version="v1",
            rules=(RuleDTO("rule-1", "+8613", "translate", "return-uas"),),
            toggles=(ToggleDTO("translation.v2", True, "remove after M6", ""),),
        ),
        created_by="ops-alice",
        created_at=1_700_000_000.0,
    )


def _managed_rule(rule_id: str = "managed-1") -> ManagedRule:
    return ManagedRule(
        rule_id=rule_id,
        name="International callers",
        match_field=MatchField.CALLING,
        match_mode=MatchMode.PREFIX,
        match_value="+8613",
        target_service=TargetService.TRANSLATION,
        enabled=True,
        target_detail="primary route",
    )


def test_order_roundtrip_is_deterministic_and_preserves_typed_models() -> None:
    order = approve(submit(_order(), "ops-alice", 1_700_000_001.0), "mgr-bob", 1_700_000_002.0)

    encoded = serialize_order(order)

    assert serialize_order(order) == encoded
    assert deserialize_order(encoded) == order
    assert deserialize_order(encoded).bundle.rules[0] == RuleDTO(
        "rule-1", "+8613", "translate", "return-uas"
    )
    assert deserialize_order(encoded).bundle.toggles[0].enabled is True


def test_v2_roundtrip_preserves_proposal_and_is_deterministic() -> None:
    order = replace(
        _order(),
        managed_rule_change=ManagedRuleChange(
            ManagedRuleChangeAction.UPDATE,
            "managed-1",
            _managed_rule(),
            7,
        ),
    )

    encoded = serialize_order(order)

    assert json.loads(encoded)["schema_version"] == 2
    assert serialize_order(order) == encoded
    assert deserialize_order(encoded) == order


def test_exact_v1_legacy_fixture_decodes_without_proposal() -> None:
    encoded = (
        '{"order":{"approved_at":null,"approver":null,"audit":[],"bundle":'
        '{"rules":[{"action":"translate","prefix":"+8613","rule_id":"rule-1",'
        '"target":"return-uas"}],"toggles":[{"enabled":true,"name":"translation.v2",'
        '"removal_condition":"remove after M6","scope":""}],"version":"v1"},'
        '"change_id":"co-1","created_at":1700000000.0,"created_by":"ops-alice",'
        '"state":"draft"},"schema_version":1}'
    )

    order = deserialize_order(encoded)

    assert order == _order()
    assert order.managed_rule_change is None


def test_audit_entry_envelope_remains_schema_v1() -> None:
    entry = AuditEntry("ops-alice", "submit", 1_700_000_001.0)

    encoded = serialize_audit_entry(entry)

    assert json.loads(encoded) == {
        "audit_entry": {"action": "submit", "actor": "ops-alice", "at": 1_700_000_001.0},
        "schema_version": 1,
    }
    assert deserialize_audit_entry(encoded) == entry


def test_decoder_rejects_malformed_managed_rule_proposals() -> None:
    encoded = serialize_order(
        replace(
            _order(),
            managed_rule_change=ManagedRuleChange(
                ManagedRuleChangeAction.CREATE,
                "managed-1",
                _managed_rule(),
                None,
            ),
        )
    )
    malformed_payloads = []
    malformed = json.loads(encoded)
    malformed["order"]["managed_rule_change"]["unexpected"] = True
    malformed_payloads.append(malformed)
    malformed = json.loads(encoded)
    malformed["order"]["managed_rule_change"]["action"] = "merge"
    malformed_payloads.append(malformed)
    malformed = json.loads(encoded)
    malformed["order"]["managed_rule_change"]["expected_revision"] = 1
    malformed_payloads.append(malformed)
    malformed = json.loads(encoded)
    malformed["order"]["managed_rule_change"]["proposed_rule"]["rule_id"] = "other"
    malformed_payloads.append(malformed)
    malformed = json.loads(encoded)
    malformed["order"]["managed_rule_change"]["proposed_rule"]["enabled"] = 1
    malformed_payloads.append(malformed)

    for malformed in malformed_payloads:
        with pytest.raises(ValueError):
            deserialize_order(json.dumps(malformed))

    duplicate_nested_key = encoded.replace(
        '"action":"create"', '"action":"create","action":"create"'
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        deserialize_order(duplicate_nested_key)


@pytest.mark.parametrize(
    ("field", "unsafe_text"),
    [
        ("created_by", "   "),
        ("created_by", "ops\u202ealice"),
        ("approver", "   "),
        ("approver", "mgr\u202ebob"),
        ("audit_actor", "   "),
        ("audit_actor", "ops\u202ealice"),
        ("audit_action", "   "),
        ("audit_action", "sub\u202emit"),
    ],
)
def test_order_serializer_rejects_unsafe_identity_and_audit_text(
    field: str, unsafe_text: str
) -> None:
    order = _order()
    if field in {"created_by", "approver"}:
        order = replace(order, **{field: unsafe_text})
    else:
        entry = AuditEntry("ops-alice", "submit", 1_700_000_001.0)
        if field == "audit_actor":
            entry = replace(entry, actor=unsafe_text)
        else:
            entry = replace(entry, action=unsafe_text)
        order = replace(order, audit=(entry,))

    with pytest.raises(ValueError):
        serialize_order(order)


@pytest.mark.parametrize(
    ("field", "unsafe_text"),
    [
        ("created_by", "   "),
        ("created_by", "ops\u202ealice"),
        ("approver", "   "),
        ("approver", "mgr\u202ebob"),
        ("actor", "   "),
        ("actor", "ops\u202ealice"),
        ("action", "   "),
        ("action", "sub\u202emit"),
    ],
)
def test_order_decoder_rejects_tampered_unsafe_identity_and_audit_text(
    field: str, unsafe_text: str
) -> None:
    encoded = serialize_order(submit(_order(), "ops-alice", 1_700_000_001.0))
    payload = json.loads(encoded)
    if field in {"created_by", "approver"}:
        payload["order"][field] = unsafe_text
    else:
        payload["order"]["audit"][0][field] = unsafe_text

    with pytest.raises(ValueError):
        deserialize_order(json.dumps(payload))


@pytest.mark.parametrize(
    "encoded",
    [
        '{"schema_version":2,"order":{}}',
        '{"schema_version":1,"schema_version":1,"order":{}}',
        json.dumps(
            {
                "schema_version": 1,
                "order": {
                    "change_id": "co-1",
                    "state": "draft",
                    "bundle": {"version": "v1", "rules": [], "toggles": []},
                    "created_by": "ops-alice",
                    "created_at": 1.0,
                    "approver": None,
                    "approved_at": None,
                    "audit": [],
                    "unexpected": True,
                },
            }
        ),
    ],
)
def test_decoder_rejects_unknown_schema_duplicate_keys_and_extra_fields(encoded: str) -> None:
    with pytest.raises(ValueError):
        deserialize_order(encoded)


def test_transition_requires_unchanged_identity_bundle_and_audit_prefix() -> None:
    submitted = submit(_order(), "ops-alice", 1_700_000_001.0)
    approved = approve(submitted, "mgr-bob", 1_700_000_002.0)

    for altered in (
        replace(approved, change_id="co-other"),
        replace(approved, created_by="ops-bob"),
        replace(approved, bundle=replace(submitted.bundle, version="v2")),
        replace(approved, audit=(replace(approved.audit[0], actor="ops-bob"), *approved.audit[1:])),
        replace(approved, audit=(*approved.audit, approved.audit[-1])),
    ):
        with pytest.raises(InvalidChangeOrderTransitionError):
            _validate_transition(submitted, altered)


@pytest.mark.parametrize("schema", ["", "bad-name", "9schema", "x" * 64])
def test_store_rejects_unsafe_or_oversized_schema(schema: str) -> None:
    with pytest.raises(ValueError, match="schema must be a safe SQL identifier"):
        PostgresChangeOrderStore(None, schema=schema)  # type: ignore[arg-type]


@pytest.mark.parametrize("action", ["reject: ", "reject: \t  "])
def test_reject_transition_requires_nonblank_reason(action: str) -> None:
    submitted = submit(_order(), "ops-alice", 1_700_000_001.0)
    rejected = reject(submitted, "ops-bob", "valid reason", 1_700_000_002.0)
    malformed = replace(
        rejected,
        audit=(
            *rejected.audit[:-1],
            replace(rejected.audit[-1], action=action),
        ),
    )
    with pytest.raises(InvalidChangeOrderTransitionError):
        _validate_transition(submitted, malformed)


def test_rollback_transition_requires_nonblank_reason() -> None:
    approved = approve(submit(_order(), "ops-alice", 1_700_000_001.0), "mgr-bob", 1_700_000_002.0)
    distributing = begin_distribution(approved, "ops-alice", 1_700_000_003.0)
    applied = mark_applied(distributing, "ops-alice", 1_700_000_004.0)

    for current in (distributing, applied):
        proposed = replace(
            current,
            state=ChangeState.ROLLED_BACK,
            audit=(
                *current.audit,
                AuditEntry(actor="ops-bob", action="roll_back: ", at=1_700_000_005.0),
            ),
        )
        with pytest.raises(InvalidChangeOrderTransitionError):
            _validate_transition(current, proposed)


class _InMemoryContractStore:
    """Test-only contract double for duplicate and revision-CAS behavior."""

    def __init__(self) -> None:
        self._orders: dict[str, list[StoredChangeOrder]] = {}

    def create(self, order: ChangeOrder) -> StoredChangeOrder:
        if order.change_id in self._orders:
            raise DuplicateChangeOrderError(order.change_id)
        stored = StoredChangeOrder(order, 1)
        self._orders[order.change_id] = [stored]
        return stored

    def append_transition(self, order: ChangeOrder, expected_revision: int) -> StoredChangeOrder:
        history = self._orders[order.change_id]
        latest = history[-1]
        if latest.revision != expected_revision:
            raise StaleChangeOrderRevisionError(order.change_id, expected_revision, latest.revision)
        _validate_transition(latest.order, order)
        stored = StoredChangeOrder(order, latest.revision + 1)
        history.append(stored)
        return stored


def test_duplicate_create_and_stale_append_are_rejected() -> None:
    store = _InMemoryContractStore()
    draft = _order()
    assert store.create(draft).revision == 1

    with pytest.raises(DuplicateChangeOrderError):
        store.create(draft)

    submitted = submit(draft, "ops-alice", 1_700_000_001.0)
    assert store.append_transition(submitted, expected_revision=1).revision == 2
    with pytest.raises(StaleChangeOrderRevisionError):
        store.append_transition(approve(submitted, "mgr-bob", 1_700_000_002.0), expected_revision=1)
