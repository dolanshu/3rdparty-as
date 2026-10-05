"""Versioned established-call dialog snapshots stored through StateStore.

Each checkpoint is one TTL-bound runtime value under the ADR-0007 key
namespace. It stores local and remote URIs, identifiers, routing data, and
sequence numbers for both dialog legs, plus explicitly selected extension
fields. It does not store full SIP messages, transaction state, media, or DUM
handles.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, NoReturn

from .store import StateStore, build_key

_SCHEMA_VERSION = 2  # See ADR-0023 (v1 decode supported)
_SCHEMA_VERSION_V1 = 1
_MAX_EXTENSION_PAYLOAD_BYTES = 4 * 1024  # See ADR-0023
_MAX_CHECKPOINT_BYTES = 16 * 1024  # See ADR-0023
_MAX_CHECKPOINT_TTL_SECONDS = 30 * 24 * 60 * 60  # See ADR-0023
_MAX_BINARY_BITS_PER_DECIMAL_DIGIT = 4


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if "\r" in value or "\n" in value or "\x00" in value:
        raise ValueError(f"{field_name} must not contain CR, LF, or NUL")
    return value


def _require_header_name(value: object, field_name: str) -> str:
    name = _require_text(value, field_name)
    if not all(
        character.isascii() and (character.isalnum() or character in "-.!%*_+`'~")
        for character in name
    ):
        raise ValueError(f"{field_name} must be a valid SIP header name")
    return name


def _require_positive_cseq(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class DialogLegCheckpoint:
    """Immutable dialog URIs, identifiers, routing data, and sequence numbers."""

    call_id: str
    local_tag: str
    remote_tag: str
    local_uri: str
    remote_uri: str
    remote_target: str
    route_set: tuple[str, ...]
    local_cseq: int
    remote_cseq: int

    def __post_init__(self) -> None:
        """Validate dialog URIs, identifiers, routes, and sequence numbers."""
        _require_text(self.call_id, "call_id")
        _require_text(self.local_tag, "local_tag")
        _require_text(self.remote_tag, "remote_tag")
        _require_text(self.local_uri, "local_uri")
        _require_text(self.remote_uri, "remote_uri")
        _require_text(self.remote_target, "remote_target")
        if not isinstance(self.route_set, tuple):
            raise ValueError("route_set must be a tuple")
        for route in self.route_set:
            _require_text(route, "route_set entry")
        _require_positive_cseq(self.local_cseq, "local_cseq")
        _require_positive_cseq(self.remote_cseq, "remote_cseq")


@dataclass(frozen=True, slots=True)
class CheckpointHeaderExtension:
    """Selected single-value headers in a namespace.

    Callers must supply only explicitly allowlisted S-CSCF context. This is an
    extension point, not arbitrary header persistence.
    """

    namespace: str
    headers: tuple[tuple[str, str], ...]  # See ADR-0023

    def __post_init__(self) -> None:
        """Validate the namespace and selected single-value headers."""
        _require_text(self.namespace, "extension namespace")
        if not isinstance(self.headers, tuple):
            raise ValueError("headers must be a tuple")

        seen_names: set[str] = set()
        for header in self.headers:
            if not isinstance(header, tuple) or len(header) != 2:
                raise ValueError("each extension header must be a (name, value) tuple")
            name, value = header
            _require_header_name(name, "header name")
            normalized_name = name.casefold()
            if normalized_name in seen_names:
                raise ValueError(f"duplicate extension header name: {name}")
            seen_names.add(normalized_name)
            if not isinstance(value, str):
                raise ValueError("each extension header must have exactly one value")
            _require_text(value, f"value for header {name}")


@dataclass(frozen=True, slots=True)
class CallStateCheckpoint:
    """Immutable snapshot of both established dialog legs, not transaction state."""

    state: Literal["established"]
    uas_leg: DialogLegCheckpoint
    uac_leg: DialogLegCheckpoint
    extensions: tuple[CheckpointHeaderExtension, ...] = ()
    owner_generation: int = 0
    committed: bool = True

    def __post_init__(self) -> None:
        """Validate the state and keep the two dialog legs independent."""
        if self.state != "established":
            raise ValueError("only established call checkpoints are supported")
        if not isinstance(self.owner_generation, int) or isinstance(self.owner_generation, bool):
            raise ValueError("owner_generation must be an integer")
        if self.owner_generation < 0:
            raise ValueError("owner_generation must be non-negative")
        if not isinstance(self.committed, bool):
            raise ValueError("committed must be a boolean")
        if not isinstance(self.uas_leg, DialogLegCheckpoint):
            raise ValueError("uas_leg must be a DialogLegCheckpoint")
        if not isinstance(self.uac_leg, DialogLegCheckpoint):
            raise ValueError("uac_leg must be a DialogLegCheckpoint")
        if self.uas_leg.call_id == self.uac_leg.call_id:
            raise ValueError("UAS and UAC legs must have distinct Call-IDs")
        if not isinstance(self.extensions, tuple):
            raise ValueError("extensions must be a tuple")

        seen_namespaces: set[str] = set()
        for extension in self.extensions:
            if not isinstance(extension, CheckpointHeaderExtension):
                raise ValueError("extensions must contain CheckpointHeaderExtension values")
            if extension.namespace in seen_namespaces:
                raise ValueError(f"duplicate extension namespace: {extension.namespace}")
            seen_namespaces.add(extension.namespace)


def _encode_leg(leg: DialogLegCheckpoint) -> dict[str, object]:
    return {
        "call_id": leg.call_id,
        "local_tag": leg.local_tag,
        "remote_tag": leg.remote_tag,
        "local_uri": leg.local_uri,
        "remote_uri": leg.remote_uri,
        "remote_target": leg.remote_target,
        "route_set": list(leg.route_set),
        "local_cseq": leg.local_cseq,
        "remote_cseq": leg.remote_cseq,
    }


def _encode_extensions(
    extensions: tuple[CheckpointHeaderExtension, ...],
) -> list[dict[str, object]]:
    return [
        {
            "namespace": extension.namespace,
            "headers": [[name, value] for name, value in extension.headers],
        }
        for extension in extensions
    ]


def _serialize_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _preflight_json_size(value: object, limit: int, error_message: str) -> None:
    serialized_size = 0

    def add_size(size: int) -> None:
        nonlocal serialized_size
        if size > limit - serialized_size:
            raise ValueError(error_message)
        serialized_size += size

    def count_string(string: str) -> None:
        add_size(2)
        for character in string:
            codepoint = ord(character)
            if 0xD800 <= codepoint <= 0xDFFF:
                raise ValueError("JSON strings must not contain surrogate code points")
            if character == '"' or character == "\\":
                add_size(2)
            elif codepoint < 0x20:
                add_size(2 if character in "\b\t\n\f\r" else 6)
            elif codepoint < 0x80:
                add_size(1)
            elif codepoint < 0x800:
                add_size(2)
            elif codepoint < 0x10000:
                add_size(3)
            else:
                add_size(4)

    def count_integer(integer: int) -> None:
        if integer == 0:
            add_size(1)
            return
        if integer < 0:
            add_size(1)
        remaining_bytes = limit - serialized_size
        if integer.bit_length() > _MAX_BINARY_BITS_PER_DECIMAL_DIGIT * remaining_bytes:
            raise ValueError(error_message)
        integer = -integer if integer < 0 else integer
        decimal_digits = 0
        while integer >= 1_000_000_000:
            integer //= 1_000_000_000
            decimal_digits += 9
            if decimal_digits > limit - serialized_size:
                raise ValueError(error_message)
        add_size(decimal_digits + len(str(integer)))

    def count_value(item: object) -> None:
        if item is None:
            add_size(4)
        elif isinstance(item, bool):
            add_size(4 if item else 5)
        elif isinstance(item, int):
            count_integer(item)
        elif isinstance(item, str):
            count_string(item)
        elif isinstance(item, list):
            add_size(2)
            has_item = False
            for nested_item in item:
                if has_item:
                    add_size(1)
                count_value(nested_item)
                has_item = True
        elif isinstance(item, dict):
            add_size(2)
            has_item = False
            for key, nested_item in item.items():
                if has_item:
                    add_size(1)
                if not isinstance(key, str):
                    raise TypeError("JSON object keys must be strings")
                count_string(key)
                add_size(1)
                count_value(nested_item)
                has_item = True
        else:
            raise TypeError(f"unsupported JSON value type: {type(item).__name__}")

    count_value(value)


def _validate_extension_payload_size(
    extensions: tuple[CheckpointHeaderExtension, ...],
) -> None:
    encoded_extensions = _encode_extensions(extensions)
    _preflight_json_size(
        encoded_extensions,
        _MAX_EXTENSION_PAYLOAD_BYTES,
        "serialized extension payload exceeds 4096 bytes",
    )
    serialized_extensions = _serialize_json(encoded_extensions)
    if len(serialized_extensions) > _MAX_EXTENSION_PAYLOAD_BYTES:
        raise ValueError("serialized extension payload exceeds 4096 bytes")


def _encode_checkpoint(checkpoint: CallStateCheckpoint) -> bytes:
    _validate_extension_payload_size(checkpoint.extensions)
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "state": checkpoint.state,
        "uas_leg": _encode_leg(checkpoint.uas_leg),
        "uac_leg": _encode_leg(checkpoint.uac_leg),
        "extensions": _encode_extensions(checkpoint.extensions),
        "owner_generation": checkpoint.owner_generation,
        "committed": checkpoint.committed,
    }
    _preflight_json_size(
        payload,
        _MAX_CHECKPOINT_BYTES,
        "serialized checkpoint exceeds 16384 bytes",
    )
    serialized_checkpoint = _serialize_json(payload)
    if len(serialized_checkpoint) > _MAX_CHECKPOINT_BYTES:
        raise ValueError("serialized checkpoint exceeds 16384 bytes")
    return serialized_checkpoint


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"invalid JSON constant: {value}")


def _require_object(
    value: object,
    expected_keys: set[str],
    object_name: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ValueError(f"{object_name} has an invalid structure")
    return value


def _require_array(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return value


def _require_integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _decode_leg(value: object, leg_name: str) -> DialogLegCheckpoint:
    leg = _require_object(
        value,
        {
            "call_id",
            "local_tag",
            "remote_tag",
            "local_uri",
            "remote_uri",
            "remote_target",
            "route_set",
            "local_cseq",
            "remote_cseq",
        },
        leg_name,
    )
    route_set = tuple(
        _require_text(route, f"{leg_name} route_set entry")
        for route in _require_array(leg["route_set"], f"{leg_name} route_set")
    )
    return DialogLegCheckpoint(
        call_id=_require_text(leg["call_id"], f"{leg_name} call_id"),
        local_tag=_require_text(leg["local_tag"], f"{leg_name} local_tag"),
        remote_tag=_require_text(leg["remote_tag"], f"{leg_name} remote_tag"),
        local_uri=_require_text(leg["local_uri"], f"{leg_name} local_uri"),
        remote_uri=_require_text(leg["remote_uri"], f"{leg_name} remote_uri"),
        remote_target=_require_text(leg["remote_target"], f"{leg_name} remote_target"),
        route_set=route_set,
        local_cseq=_require_integer(leg["local_cseq"], f"{leg_name} local_cseq"),
        remote_cseq=_require_integer(leg["remote_cseq"], f"{leg_name} remote_cseq"),
    )


def _decode_extension(value: object, index: int) -> CheckpointHeaderExtension:
    extension = _require_object(value, {"namespace", "headers"}, f"extension {index}")
    headers: list[tuple[str, str]] = []
    for header_index, item in enumerate(
        _require_array(extension["headers"], f"extension {index} headers")
    ):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"extension {index} header {header_index} has an invalid structure")
        name = _require_text(item[0], f"extension {index} header name")
        header_value = _require_text(item[1], f"extension {index} header value")
        headers.append((name, header_value))
    return CheckpointHeaderExtension(
        namespace=_require_text(extension["namespace"], f"extension {index} namespace"),
        headers=tuple(headers),
    )


def _decode_checkpoint(value: bytes) -> CallStateCheckpoint:
    if not isinstance(value, bytes):
        raise ValueError("stored checkpoint must be bytes")
    if len(value) > _MAX_CHECKPOINT_BYTES:
        raise ValueError("stored checkpoint exceeds 16384 bytes")
    try:
        raw: object = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except ValueError as error:
        raise ValueError("stored checkpoint must be valid UTF-8 JSON") from error

    required_keys = {"schema_version", "state", "uas_leg", "uac_leg", "extensions"}
    if not isinstance(raw, dict):
        raise ValueError("checkpoint has an invalid structure")
    extra_keys = set(raw) - required_keys - {"owner_generation", "committed"}
    if extra_keys:
        raise ValueError(f"checkpoint has unexpected keys: {sorted(extra_keys)}")
    if not required_keys <= set(raw):
        raise ValueError("checkpoint has an invalid structure")
    payload = raw
    schema_version = _require_integer(payload["schema_version"], "schema_version")
    if schema_version not in (_SCHEMA_VERSION, _SCHEMA_VERSION_V1):
        raise ValueError(f"unsupported checkpoint schema version: {schema_version}")
    owner_generation = 0
    committed = True
    if schema_version >= _SCHEMA_VERSION:
        owner_generation = _require_integer(payload.get("owner_generation", 0), "owner_generation")
        if owner_generation < 0:
            raise ValueError("owner_generation must be non-negative")
        committed_value = payload.get("committed", False)
        if not isinstance(committed_value, bool):
            raise ValueError("committed must be a boolean")
        committed = committed_value
    state = _require_text(payload["state"], "state")
    if state != "established":
        raise ValueError(f"unsupported checkpoint state: {state}")
    extensions = tuple(
        _decode_extension(extension, index)
        for index, extension in enumerate(_require_array(payload["extensions"], "extensions"))
    )
    _validate_extension_payload_size(extensions)
    return CallStateCheckpoint(
        state="established",
        uas_leg=_decode_leg(payload["uas_leg"], "uas_leg"),
        uac_leg=_decode_leg(payload["uac_leg"], "uac_leg"),
        extensions=extensions,
        owner_generation=owner_generation,
        committed=committed,
    )


def _normalize_allowed_header_namespaces(
    allowed_header_namespaces: Mapping[str, Iterable[str]],
) -> dict[str, frozenset[str]]:
    if not isinstance(allowed_header_namespaces, Mapping):
        raise ValueError("allowed_header_namespaces must be a mapping")

    normalized: dict[str, frozenset[str]] = {}
    for namespace, header_names in allowed_header_namespaces.items():
        namespace = _require_text(namespace, "allowed header namespace")
        if isinstance(header_names, (str, bytes)) or not isinstance(header_names, Iterable):
            raise ValueError("allowed header names must be an iterable of names")
        normalized[namespace] = frozenset(
            _require_header_name(name, f"allowed header name in {namespace}").casefold()
            for name in header_names
        )
    return normalized


class CallStateCheckpointRepository:
    """Store each two-leg checkpoint as one TTL-bound StateStore value."""

    def __init__(
        self,
        store: StateStore,
        ttl_seconds: int,
        allowed_header_namespaces: Mapping[str, Iterable[str]],
    ) -> None:
        """Create a repository with an integer TTL and copied header allowlist."""
        if (
            not isinstance(ttl_seconds, int)
            or isinstance(ttl_seconds, bool)
            or ttl_seconds <= 0
            or ttl_seconds > _MAX_CHECKPOINT_TTL_SECONDS
        ):
            raise ValueError("ttl_seconds must be a positive integer no greater than 2592000")
        self._store = store
        self._ttl_seconds = ttl_seconds
        self._allowed_header_namespaces = _normalize_allowed_header_namespaces(
            allowed_header_namespaces
        )

    def _validate_extensions(self, checkpoint: CallStateCheckpoint) -> None:
        # See ADR-0023: persist only selected, explicitly allowlisted context.
        for extension in checkpoint.extensions:
            allowed_header_names = self._allowed_header_namespaces.get(extension.namespace)
            if allowed_header_names is None:
                raise ValueError(f"extension namespace is not allowlisted: {extension.namespace}")
            for name, _ in extension.headers:
                if name.casefold() not in allowed_header_names:
                    raise ValueError(
                        f"header {name} is not allowlisted for namespace {extension.namespace}"
                    )

    def save(
        self,
        case: str,
        call_key: str,
        checkpoint: CallStateCheckpoint,
    ) -> None:
        """Save a complete checkpoint in one StateStore write."""
        _require_text(case, "case")
        _require_text(call_key, "call_key")
        if not isinstance(checkpoint, CallStateCheckpoint):
            raise ValueError("checkpoint must be a CallStateCheckpoint")
        self._validate_extensions(checkpoint)
        encoded_checkpoint = _encode_checkpoint(checkpoint)
        # See ADR-0023: persist both legs together as one bounded TTL value.
        self._store.set(
            build_key(case, "call", call_key),
            encoded_checkpoint,
            ttl_seconds=self._ttl_seconds,
        )

    def load(self, case: str, call_key: str) -> CallStateCheckpoint | None:
        """Load and strictly decode a checkpoint, or return ``None`` if absent."""
        _require_text(case, "case")
        _require_text(call_key, "call_key")
        value = self._store.get(build_key(case, "call", call_key))
        if value is None:
            return None
        checkpoint = _decode_checkpoint(value)
        self._validate_extensions(checkpoint)
        return checkpoint

    def save_if_generation(
        self,
        case: str,
        call_key: str,
        checkpoint: CallStateCheckpoint,
        *,
        expected_generation: int | None,
    ) -> bool:
        """Compare-and-swap save on ``owner_generation`` (ADR-0023 fencing seam).

        Returns ``True`` when the write succeeds. When ``expected_generation`` is
        ``None``, the key must be absent. Otherwise the stored generation must match.
        """
        _require_text(case, "case")
        _require_text(call_key, "call_key")
        if expected_generation is not None and (
            not isinstance(expected_generation, int)
            or isinstance(expected_generation, bool)
            or expected_generation < 0
        ):
            raise ValueError("expected_generation must be a non-negative integer or None")
        existing = self.load(case=case, call_key=call_key)
        if expected_generation is None:
            if existing is not None:
                return False
        elif existing is None or existing.owner_generation != expected_generation:
            return False
        self.save(case=case, call_key=call_key, checkpoint=checkpoint)
        return True


@dataclass(frozen=True, slots=True)
class CallCheckpointCommit:
    """Owner generation bump and durable-commit gate before native SIP side effects.

    See ADR-0023: dependent SIP side effects require ``committed=True`` on the
    checkpoint record that was durably acknowledged in Redis.
    """

    checkpoint: CallStateCheckpoint

    def with_bumped_generation(self) -> CallStateCheckpoint:
        """Return a new checkpoint with generation incremented and ``committed=False``."""
        return CallStateCheckpoint(
            state=self.checkpoint.state,
            uas_leg=self.checkpoint.uas_leg,
            uac_leg=self.checkpoint.uac_leg,
            extensions=self.checkpoint.extensions,
            owner_generation=self.checkpoint.owner_generation + 1,
            committed=False,
        )

    def mark_committed(self) -> CallStateCheckpoint:
        """Return a checkpoint marked committed after a successful durable write."""
        return CallStateCheckpoint(
            state=self.checkpoint.state,
            uas_leg=self.checkpoint.uas_leg,
            uac_leg=self.checkpoint.uac_leg,
            extensions=self.checkpoint.extensions,
            owner_generation=self.checkpoint.owner_generation,
            committed=True,
        )

    def require_committed_before_side_effect(self) -> None:
        """Fail closed when native SIP side effects would depend on an uncommitted record."""
        if not self.checkpoint.committed:
            raise RuntimeError(
                "checkpoint is not committed; durable write must complete before SIP side effects"
            )


class CallCheckpointLifecycle:
    """TTL renewal and terminal cleanup for active call checkpoints."""

    def __init__(self, repository: CallStateCheckpointRepository) -> None:
        """Wrap a repository for TTL renew and terminal delete helpers."""
        self._repository = repository
        self._store = repository._store
        self._default_ttl = repository._ttl_seconds

    def renew(self, case: str, call_key: str, ttl_seconds: int | None = None) -> bool:
        """Re-arm TTL for an existing checkpoint key; returns ``False`` when absent."""
        _require_text(case, "case")
        _require_text(call_key, "call_key")
        key = build_key(case, "call", call_key)
        if self._store.get(key) is None:
            return False
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        if (
            not isinstance(ttl, int)
            or isinstance(ttl, bool)
            or ttl <= 0
            or ttl > _MAX_CHECKPOINT_TTL_SECONDS
        ):
            raise ValueError("ttl_seconds must be a positive integer no greater than 2592000")
        self._store.expire(key, float(ttl))
        return True

    def mark_terminal_and_delete(self, case: str, call_key: str) -> None:
        """Remove the checkpoint after the call reaches a terminal state."""
        _require_text(case, "case")
        _require_text(call_key, "call_key")
        self._store.delete(build_key(case, "call", call_key))
