"""Unit coverage for console authentication primitives. REQ-S-4, ADR-0024."""

from __future__ import annotations

import base64
import hashlib
import json
import re

import pytest

from as_config_service.auth import (
    MAX_PASSWORD_UTF8_BYTES,
    InvalidPasswordVerifierError,
    IssuedSession,
    PostgresConsoleAuthStore,
    _deserialize_roles,
    _finite_time,
    _user_id,
    hash_password,
    validate_password,
    verify_password,
)
from as_console.access import Role

pytestmark = pytest.mark.unit


def _verifier(password: str, iterations: int = 1) -> str:
    salt = bytes(range(16))
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, 32)

    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    return f"pbkdf2-sha256$v1${iterations}$32${encode(salt)}${encode(digest)}"


def test_password_verifier_round_trips_exact_utf8_without_normalization() -> None:
    password = "Pässphrase-12"
    verifier = hash_password(password)

    assert re.fullmatch(
        r"pbkdf2-sha256\$v1\$600000\$32\$[A-Za-z0-9_-]{22}\$[A-Za-z0-9_-]{43}",
        verifier,
    )
    assert verify_password(password, verifier)
    assert not verify_password("Pa\u0308ssphrase-12", verifier)
    assert verifier.endswith(
        base64.urlsafe_b64encode(
            hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                base64.urlsafe_b64decode(verifier.split("$")[4] + "=="),
                600_000,
                32,
            )
        )
        .decode("ascii")
        .rstrip("=")
    )


@pytest.mark.parametrize(
    "verifier",
    [
        "pbkdf2-sha256$v1$1$32$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "pbkdf2-sha256$v1$01$32$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "pbkdf2-sha256$v1$2000001$32$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "pbkdf2-sha256$v1$600000$31$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "pbkdf2-sha256$v1$600000$32$AAAAAAAAAAAAAAAAAAAAAB$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "pbkdf2-sha256$v1$600000$32$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA$extra",
        "pbkdf2-sha256$v2$600000$32$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "pbkdf2-sha256$v1$0$32$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    ],
)
def test_password_verifier_rejects_malformed_noncanonical_and_excessive_values(
    verifier: str,
) -> None:
    with pytest.raises(InvalidPasswordVerifierError):
        verify_password("a sufficiently long password", verifier)


def test_password_minimum_and_wrong_password() -> None:
    with pytest.raises(ValueError, match="12 characters"):
        validate_password("too-short")

    verifier = _verifier("correct horse battery")

    assert validate_password("correct horse battery") == b"correct horse battery"
    assert verify_password("correct horse battery", verifier)
    assert not verify_password("wrong horse battery", verifier)


@pytest.mark.parametrize("password", ["p" * 1_024, "é" * 512])
def test_password_accepts_exactly_1024_utf8_bytes_with_mocked_pbkdf2(
    password: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hashlib, "pbkdf2_hmac", lambda *args, **kwargs: b"x" * 32)

    assert MAX_PASSWORD_UTF8_BYTES == 1_024
    assert len(validate_password(password)) == MAX_PASSWORD_UTF8_BYTES
    assert hash_password(password).startswith("pbkdf2-sha256$v1$600000$32$")


@pytest.mark.parametrize("password", ["p" * 1_025, "é" * 513])
def test_password_rejects_more_than_1024_utf8_bytes_before_pbkdf2(
    password: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_pbkdf2(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("oversized passwords must be rejected before PBKDF2")

    monkeypatch.setattr(hashlib, "pbkdf2_hmac", unexpected_pbkdf2)

    with pytest.raises(ValueError, match="1024 UTF-8 bytes"):
        hash_password(password)


@pytest.mark.parametrize("user_id", ["", " ", "with space", "../admin", "x" * 129])
def test_user_id_must_be_safe_and_nonblank(user_id: str) -> None:
    with pytest.raises(ValueError, match="safe, nonblank"):
        _user_id(user_id)


@pytest.mark.parametrize("timestamp", [float("inf"), float("-inf"), float("nan"), True])
def test_account_timestamps_must_be_finite_numbers(timestamp: object) -> None:
    with pytest.raises((TypeError, ValueError), match="finite number"):
        _finite_time(timestamp, "created_at")


def test_roles_decode_strictly_through_shared_role_enum() -> None:
    encoded = json.dumps([Role.ADMIN.value, Role.VIEWER.value], separators=(",", ":"))

    assert _deserialize_roles(encoded) == frozenset({Role.ADMIN, Role.VIEWER})

    for invalid in (
        '["viewer","viewer"]',
        '["VIEWER"]',
        '["unknown"]',
        '["viewer", "admin"]',
        '{"role":"admin"}',
        '["viewer",1]',
    ):
        with pytest.raises(ValueError, match="stored roles are invalid"):
            _deserialize_roles(invalid)


@pytest.mark.parametrize("prefix", ["", "bad-name", "9prefix", "x" * 54])
def test_store_rejects_unsafe_prefix(prefix: str) -> None:
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresConsoleAuthStore(None, prefix=prefix)  # type: ignore[arg-type]


@pytest.mark.parametrize("schema", ["", "bad-name", "9schema", "x" * 64])
def test_store_rejects_unsafe_schema(schema: str) -> None:
    with pytest.raises(ValueError, match="schema must be a safe SQL identifier"):
        PostgresConsoleAuthStore(None, schema=schema)  # type: ignore[arg-type]


def test_issued_session_tokens_are_unpadded_256_bit_values_and_hidden_from_repr() -> None:
    token = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii").rstrip("=")
    csrf = base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode("ascii").rstrip("=")
    issued = IssuedSession(token, csrf, 10.0, 20.0)

    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", issued.token)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", issued.csrf_token)
    assert token not in repr(issued)
    assert csrf not in repr(issued)
