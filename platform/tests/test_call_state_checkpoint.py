"""Contract cases for REQ-NF-1/D10 checkpoint groundwork under ADR-0023."""

from __future__ import annotations

import json
from typing import Any

import pytest

import as_platform.state.call_checkpoint as call_checkpoint_module
from as_platform.state.call_checkpoint import (
    CallStateCheckpoint,
    CallStateCheckpointRepository,
    CheckpointHeaderExtension,
    DialogLegCheckpoint,
)
from as_platform.state.in_memory import InMemoryStateStore

pytestmark = pytest.mark.contract


class FakeClock:
    """A deterministic clock for the in-memory state store."""

    def __init__(self) -> None:
        self.now_value = 1_000.0

    def __call__(self) -> float:
        return self.now_value


class RecordingInMemoryStateStore(InMemoryStateStore):
    """An in-memory store that records checkpoint writes."""

    def __init__(self, now: FakeClock) -> None:
        super().__init__(now=now)
        self.writes: list[tuple[str, bytes, float | None]] = []

    def set(self, key: str, value: bytes, ttl_seconds: float | None = None) -> None:
        self.writes.append((key, value, ttl_seconds))
        super().set(key, value, ttl_seconds)


def _checkpoint_with_extension(
    extension: CheckpointHeaderExtension,
) -> CallStateCheckpoint:
    return CallStateCheckpoint(
        state="established",
        uas_leg=DialogLegCheckpoint(
            call_id="uas-call",
            local_tag="uas-local",
            remote_tag="uas-remote",
            local_uri="sip:translation@example.net",
            remote_uri="sip:alice@example.net",
            remote_target="sip:alice@example.net",
            route_set=(),
            local_cseq=1,
            remote_cseq=1,
        ),
        uac_leg=DialogLegCheckpoint(
            call_id="uac-call",
            local_tag="uac-local",
            remote_tag="uac-remote",
            local_uri="sip:translation@example.net",
            remote_uri="sip:bob@example.net",
            remote_target="sip:bob@example.net",
            route_set=(),
            local_cseq=1,
            remote_cseq=1,
        ),
        extensions=(extension,),
    )


def test_ack_established_checkpoint_round_trips_as_one_bytes_value() -> None:
    case = "translation"
    call_key = "opaque-7f3a1d92"
    store = RecordingInMemoryStateStore(now=FakeClock())
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces={"urn:example:translation": frozenset({"P-Asserted-Identity"})},
    )
    checkpoint = CallStateCheckpoint(
        state="established",
        uas_leg=DialogLegCheckpoint(
            call_id="uas-dialog-2c5a@ims.example.net",
            local_tag="uas-local-a31f",
            remote_tag="uas-remote-77b2",
            local_uri="sip:translation@ims.example.net",
            remote_uri="sip:alice@home.example.net",
            remote_target="sip:alice@ue-a.example.net",
            route_set=("sip:scscf-ingress.ims.example.net;lr",),
            local_cseq=42,
            remote_cseq=18,
        ),
        uac_leg=DialogLegCheckpoint(
            call_id="uac-dialog-91f7@ims.example.net",
            local_tag="uac-local-4d0c",
            remote_tag="uac-remote-f829",
            local_uri="sip:alice@home.example.net",
            remote_uri="sip:bob@example.net",
            remote_target="sip:+15551230002@peer.example.net",
            route_set=(
                "sip:scscf-egress.ims.example.net;lr",
                "sip:edge-sbc.example.net;lr",
            ),
            local_cseq=7,
            remote_cseq=63,
        ),
        extensions=(
            CheckpointHeaderExtension(
                namespace="urn:example:translation",
                headers=(
                    (
                        "p-asserted-identity",
                        "sip:alice@home.example.net",
                    ),
                ),
            ),
        ),
    )

    assert checkpoint.uas_leg.call_id != checkpoint.uac_leg.call_id
    expected_uas_uris = (
        "sip:translation@ims.example.net",
        "sip:alice@home.example.net",
    )
    expected_uac_uris = (
        "sip:alice@home.example.net",
        "sip:bob@example.net",
    )
    assert (checkpoint.uas_leg.local_uri, checkpoint.uas_leg.remote_uri) == expected_uas_uris
    assert (checkpoint.uac_leg.local_uri, checkpoint.uac_leg.remote_uri) == expected_uac_uris

    repository.save(case=case, call_key=call_key, checkpoint=checkpoint)

    expected_key = "as:translation:call:opaque-7f3a1d92"
    assert len(store.writes) == 1
    written_key, written_value, written_ttl = store.writes[0]
    assert written_key == expected_key
    assert isinstance(written_value, bytes)
    assert written_ttl == 120
    assert store.get(expected_key) == written_value
    loaded_checkpoint = repository.load(case=case, call_key=call_key)
    assert loaded_checkpoint is not None
    assert (loaded_checkpoint.uas_leg.local_uri, loaded_checkpoint.uas_leg.remote_uri) == (
        expected_uas_uris
    )
    assert (loaded_checkpoint.uac_leg.local_uri, loaded_checkpoint.uac_leg.remote_uri) == (
        expected_uac_uris
    )
    assert loaded_checkpoint == checkpoint


@pytest.mark.parametrize(
    "ttl_seconds",
    [0, -1, True, 0.5, 1.5, 120.0, 2_592_001],
)
def test_repository_requires_positive_integer_ttl(
    ttl_seconds: Any,
) -> None:
    with pytest.raises(ValueError):
        CallStateCheckpointRepository(
            store=InMemoryStateStore(now=FakeClock()),
            ttl_seconds=ttl_seconds,
            allowed_header_namespaces={},
        )


def test_repository_preserves_max_ttl_as_exact_seconds() -> None:
    store = RecordingInMemoryStateStore(now=FakeClock())
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=2_592_000,
        allowed_header_namespaces={"urn:example:translation": frozenset()},
    )
    checkpoint = _checkpoint_with_extension(
        CheckpointHeaderExtension(namespace="urn:example:translation", headers=())
    )

    repository.save(case="translation", call_key="opaque-call", checkpoint=checkpoint)

    assert store.writes[0][2] == 2_592_000
    assert type(store.writes[0][2]) is int


def test_repository_does_not_save_oversized_extension_payload() -> None:
    store = RecordingInMemoryStateStore(now=FakeClock())
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces={"urn:example:translation": frozenset({"X-Context"})},
    )
    checkpoint = _checkpoint_with_extension(
        CheckpointHeaderExtension(
            namespace="urn:example:translation",
            headers=(("X-Context", "x" * 5_000),),
        )
    )

    with pytest.raises(ValueError, match="extension payload"):
        repository.save(case="translation", call_key="opaque-call", checkpoint=checkpoint)

    assert store.writes == []


def test_repository_preflights_large_extension_before_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RecordingInMemoryStateStore(now=FakeClock())
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces={"urn:example:translation": frozenset({"X-Context"})},
    )
    checkpoint = _checkpoint_with_extension(
        CheckpointHeaderExtension(
            namespace="urn:example:translation",
            headers=(("X-Context", "x" * 1_000_000),),
        )
    )

    def fail_if_serialized(_value: object) -> bytes:
        pytest.fail("oversized extension reached JSON serialization")

    monkeypatch.setattr(call_checkpoint_module, "_serialize_json", fail_if_serialized)

    with pytest.raises(ValueError, match="extension payload"):
        repository.save(case="translation", call_key="opaque-call", checkpoint=checkpoint)

    assert store.writes == []


def test_repository_preflights_large_route_before_checkpoint_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RecordingInMemoryStateStore(now=FakeClock())
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces={},
    )
    baseline = _checkpoint_with_extension(
        CheckpointHeaderExtension(namespace="urn:example:translation", headers=())
    )
    checkpoint = CallStateCheckpoint(
        state="established",
        uas_leg=DialogLegCheckpoint(
            call_id="uas-call",
            local_tag="uas-local",
            remote_tag="uas-remote",
            local_uri="sip:translation@example.net",
            remote_uri="sip:alice@example.net",
            remote_target="sip:alice@example.net",
            route_set=("sip:" + "x" * 1_000_000,),
            local_cseq=1,
            remote_cseq=1,
        ),
        uac_leg=baseline.uac_leg,
    )
    serialized_values: list[object] = []
    serialize_json = call_checkpoint_module._serialize_json

    def fail_if_checkpoint_serialized(value: object) -> bytes:
        serialized_values.append(value)
        if isinstance(value, dict):
            pytest.fail("oversized checkpoint reached JSON serialization")
        return serialize_json(value)

    monkeypatch.setattr(call_checkpoint_module, "_serialize_json", fail_if_checkpoint_serialized)

    with pytest.raises(ValueError, match="serialized checkpoint exceeds"):
        repository.save(case="translation", call_key="opaque-call", checkpoint=checkpoint)

    assert serialized_values == [[]]
    assert store.writes == []


def test_repository_rejects_surrogate_before_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RecordingInMemoryStateStore(now=FakeClock())
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces={"urn:example:translation": frozenset({"X-Context"})},
    )
    checkpoint = _checkpoint_with_extension(
        CheckpointHeaderExtension(
            namespace="urn:example:translation",
            headers=(("X-Context", "\ud800"),),
        )
    )

    def fail_if_serialized(_value: object) -> bytes:
        pytest.fail("surrogate reached JSON serialization")

    monkeypatch.setattr(call_checkpoint_module, "_serialize_json", fail_if_serialized)

    with pytest.raises(ValueError, match="surrogate code points"):
        repository.save(case="translation", call_key="opaque-call", checkpoint=checkpoint)

    assert store.writes == []


def test_repository_does_not_save_oversized_checkpoint() -> None:
    store = RecordingInMemoryStateStore(now=FakeClock())
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces={},
    )
    baseline = _checkpoint_with_extension(
        CheckpointHeaderExtension(namespace="urn:example:translation", headers=())
    )
    checkpoint = CallStateCheckpoint(
        state="established",
        uas_leg=DialogLegCheckpoint(
            call_id="uas-call",
            local_tag="uas-local",
            remote_tag="uas-remote",
            local_uri="sip:translation@example.net",
            remote_uri="sip:alice@example.net",
            remote_target="sip:alice@example.net",
            route_set=("sip:" + "x" * 16_384,),
            local_cseq=1,
            remote_cseq=1,
        ),
        uac_leg=baseline.uac_leg,
    )

    with pytest.raises(ValueError, match="serialized checkpoint exceeds"):
        repository.save(case="translation", call_key="opaque-call", checkpoint=checkpoint)

    assert store.writes == []


def test_repository_rejects_oversized_stored_checkpoint_before_decoding() -> None:
    store = RecordingInMemoryStateStore(now=FakeClock())
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces={},
    )
    store.set(
        "as:translation:call:opaque-call",
        b" " * (16 * 1024 + 1),
        ttl_seconds=120,
    )

    with pytest.raises(ValueError, match="stored checkpoint exceeds"):
        repository.load(case="translation", call_key="opaque-call")


@pytest.mark.parametrize(
    ("header_value", "error_match"),
    [
        ("x" * 4_096, "extension payload"),
        (["sip:alice@example.net", "tel:+15551230001"], "header value"),
    ],
    ids=("oversized_decoded_extension", "multi_valued_header"),
)
def test_repository_rejects_oversized_or_multi_valued_stored_extensions(
    header_value: object,
    error_match: str,
) -> None:
    store = RecordingInMemoryStateStore(now=FakeClock())
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces={"urn:example:translation": frozenset({"X-Context"})},
    )
    baseline = _checkpoint_with_extension(
        CheckpointHeaderExtension(namespace="urn:example:translation", headers=())
    )
    repository.save(case="translation", call_key="opaque-call", checkpoint=baseline)

    key, value, ttl_seconds = store.writes[0]
    payload = json.loads(value)
    payload["extensions"] = [
        {
            "namespace": "urn:example:translation",
            "headers": [["X-Context", header_value]],
        }
    ]
    stored_value = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    assert len(stored_value) < 16 * 1024
    store.set(key, stored_value, ttl_seconds=ttl_seconds)

    with pytest.raises(ValueError, match=error_match):
        repository.load(case="translation", call_key="opaque-call")


@pytest.mark.parametrize(
    ("namespace", "header_name"),
    [
        ("urn:example:unconfigured", "P-Asserted-Identity"),
        ("urn:example:translation", "X-Unapproved"),
    ],
    ids=("unconfigured_namespace", "unapproved_header"),
)
def test_repository_rejects_unallowlisted_extension_headers(
    namespace: str,
    header_name: str,
) -> None:
    store = RecordingInMemoryStateStore(now=FakeClock())
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces={"urn:example:translation": frozenset({"P-Asserted-Identity"})},
    )
    checkpoint = _checkpoint_with_extension(
        CheckpointHeaderExtension(
            namespace=namespace,
            headers=((header_name, "sip:alice@home.example.net"),),
        )
    )

    with pytest.raises(ValueError):
        repository.save(case="translation", call_key="opaque-call", checkpoint=checkpoint)

    assert store.writes == []


@pytest.mark.parametrize(
    "current_allowed_header_namespaces",
    [
        {},
        {"urn:example:translation": frozenset({"X-New-Route"})},
    ],
    ids=("namespace_removed", "header_removed"),
)
def test_repository_rejects_stored_extension_when_allowlist_changes(
    current_allowed_header_namespaces: dict[str, frozenset[str]],
) -> None:
    store = RecordingInMemoryStateStore(now=FakeClock())
    old_repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces={"urn:example:translation": frozenset({"X-Old-Route"})},
    )
    checkpoint = _checkpoint_with_extension(
        CheckpointHeaderExtension(
            namespace="urn:example:translation",
            headers=(("X-Old-Route", "sip:alice@home.example.net"),),
        )
    )
    old_repository.save(case="translation", call_key="opaque-call", checkpoint=checkpoint)

    current_repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=120,
        allowed_header_namespaces=current_allowed_header_namespaces,
    )

    with pytest.raises(ValueError):
        current_repository.load(case="translation", call_key="opaque-call")


@pytest.mark.parametrize(
    "header_value",
    [
        "sip:alice@home.example.net\rX-Injection: yes",
        "sip:alice@home.example.net\nX-Injection: yes",
        "sip:alice@home.example.net\x00X-Injection",
    ],
    ids=("carriage_return", "line_feed", "nul"),
)
def test_checkpoint_header_extension_rejects_header_value_injection(
    header_value: str,
) -> None:
    with pytest.raises(ValueError):
        CheckpointHeaderExtension(
            namespace="urn:example:translation",
            headers=(("P-Asserted-Identity", header_value),),
        )


def test_checkpoint_header_extension_rejects_case_insensitive_duplicate_names() -> None:
    with pytest.raises(ValueError, match="duplicate extension header name"):
        CheckpointHeaderExtension(
            namespace="urn:example:translation",
            headers=(("X-Context", "first"), ("x-context", "second")),
        )
