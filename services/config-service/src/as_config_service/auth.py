"""PostgreSQL-backed console accounts, password verification, and sessions.

The caller owns the injected connection and may coordinate mutations with other
governance writes by passing ``commit=False``. See ADR-0024 and REQ-S-4.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from as_console.access import Principal, Role

_IDENTIFIER = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
_USER_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.@+-]{0,127}\Z")
_TOKEN = re.compile(r"\A[A-Za-z0-9_-]{43}\Z")
_CURRENT_ITERATIONS = 600_000
_MAX_STORED_ITERATIONS = 2_000_000
MAX_PASSWORD_UTF8_BYTES = 1_024
_KEY_BYTES = 32
_SALT_BYTES = 16
_DEFAULT_SESSION_TTL_SECONDS = 28_800
_MAX_SESSION_TTL_SECONDS = 28_800
_DUMMY_VERIFIER = (
    "pbkdf2-sha256$v1$600000$32$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)


class _Cursor(Protocol):
    def execute(self, sql: str, params: tuple[object, ...] = ()) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class BootstrapAlreadyCompleteError(Exception):
    """Raised when first-admin bootstrap is no longer available."""

    def __init__(self) -> None:
        """Initialize with a generic message that omits account details."""
        super().__init__("first administrator bootstrap is unavailable")


class ConsoleBootstrapRequiredError(Exception):
    """Raised when ordinary account creation precedes first-admin bootstrap."""

    def __init__(self) -> None:
        """Initialize with a generic message that omits account details."""
        super().__init__("first administrator bootstrap is required")


class _PasswordTooLongError(ValueError):
    """Raised before encoding or deriving a verifier for oversized input."""


class DuplicateConsoleUserError(Exception):
    """Raised when a user identifier is already present."""

    def __init__(self) -> None:
        """Initialize with a generic message that omits the identifier."""
        super().__init__("user already exists")


class ConsoleUserNotFoundError(LookupError):
    """Raised when a requested account does not exist or is unavailable."""

    def __init__(self) -> None:
        """Initialize with a generic message that omits the identifier."""
        super().__init__("user is unavailable")


class LastEnabledConsoleAdminError(Exception):
    """Raised when an update would remove the last enabled administrator."""

    def __init__(self) -> None:
        """Initialize with a generic message that omits account details."""
        super().__init__("the last enabled administrator cannot be removed")


class InvalidPasswordVerifierError(ValueError):
    """Raised when a persisted verifier is malformed or outside safe bounds."""

    def __init__(self) -> None:
        """Initialize with a generic message that omits stored data."""
        super().__init__("stored password verifier is invalid")


@dataclass(frozen=True)
class ConsoleUser:
    """An account view that never contains password verifier material."""

    user_id: str
    roles: frozenset[Role]
    enabled: bool
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class IssuedSession:
    """A newly issued session; raw tokens are returned only to the caller."""

    token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    created_at: float
    expires_at: float


def _finite_time(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _user_id(value: object) -> str:
    if not isinstance(value, str) or not _USER_ID.fullmatch(value):
        raise ValueError("user_id must be a safe, nonblank identifier")
    return value


def _password_bytes(password: object) -> bytes:
    if not isinstance(password, str):
        raise TypeError("password must be text")
    if len(password) > MAX_PASSWORD_UTF8_BYTES:
        raise _PasswordTooLongError("password must not exceed 1024 UTF-8 bytes")
    try:
        encoded = password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("password must be valid UTF-8 text") from exc
    if len(encoded) > MAX_PASSWORD_UTF8_BYTES:
        raise _PasswordTooLongError("password must not exceed 1024 UTF-8 bytes")
    return encoded


def validate_password(password: object) -> bytes:
    """Return exact UTF-8 password bytes after enforcing the minimum length."""
    encoded = _password_bytes(password)
    if len(password) < 12:  # type: ignore[arg-type]
        raise ValueError("password must contain at least 12 characters")
    return encoded


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode_canonical(value: str, expected_bytes: int) -> bytes:
    expected_chars = (expected_bytes * 8 + 5) // 6
    if len(value) != expected_chars or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise InvalidPasswordVerifierError()
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error) as exc:
        raise InvalidPasswordVerifierError() from exc
    if len(decoded) != expected_bytes or _b64encode(decoded) != value:
        raise InvalidPasswordVerifierError()
    return decoded


def hash_password(password: str) -> str:
    """Create an ADR-0024 v1 PBKDF2-HMAC-SHA256 verifier."""
    password_bytes = validate_password(password)
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password_bytes, salt, _CURRENT_ITERATIONS, dklen=_KEY_BYTES
    )
    return (
        f"pbkdf2-sha256$v1${_CURRENT_ITERATIONS}${_KEY_BYTES}$"
        f"{_b64encode(salt)}${_b64encode(digest)}"
    )


def _decode_verifier(verifier: object) -> tuple[int, bytes, bytes]:
    if not isinstance(verifier, str):
        raise InvalidPasswordVerifierError()
    parts = verifier.split("$")
    if len(parts) != 6 or parts[0:2] != ["pbkdf2-sha256", "v1"]:
        raise InvalidPasswordVerifierError()
    if (
        not parts[2].isascii()
        or not parts[2].isdecimal()
        or len(parts[2]) > 7
        or str(int(parts[2])) != parts[2]
    ):
        raise InvalidPasswordVerifierError()
    if parts[2].startswith("+"):
        raise InvalidPasswordVerifierError()
    iterations = int(parts[2])
    if not 1 <= iterations <= _MAX_STORED_ITERATIONS or parts[3] != str(_KEY_BYTES):
        raise InvalidPasswordVerifierError()
    salt = _b64decode_canonical(parts[4], _SALT_BYTES)
    digest = _b64decode_canonical(parts[5], _KEY_BYTES)
    return iterations, salt, digest


def verify_password(password: str, verifier: str) -> bool:
    """Verify exact UTF-8 password bytes against a bounded stored verifier."""
    password_bytes = _password_bytes(password)
    iterations, salt, expected = _decode_verifier(verifier)
    actual = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, iterations, dklen=_KEY_BYTES)
    return hmac.compare_digest(actual, expected)


def _serialize_roles(roles: object) -> str:
    if isinstance(roles, (str, bytes)):
        raise TypeError("roles must contain Role values")
    if not isinstance(roles, Iterable):
        raise TypeError("roles must be iterable")
    values = list(roles)
    if any(type(role) is not Role for role in values):
        raise TypeError("roles must contain Role values")
    serialized = sorted(role.value for role in values)
    if len(serialized) != len(set(serialized)):
        raise ValueError("roles must not contain duplicates")
    return json.dumps(serialized, separators=(",", ":"))


def _deserialize_roles(value: object) -> frozenset[Role]:
    if not isinstance(value, str):
        raise ValueError("stored roles are invalid")
    try:
        roles = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("stored roles are invalid") from exc
    if (
        type(roles) is not list
        or any(type(role) is not str for role in roles)
        or roles != sorted(set(roles))
        or json.dumps(roles, separators=(",", ":")) != value
    ):
        raise ValueError("stored roles are invalid")
    try:
        return frozenset(Role(role) for role in roles)
    except ValueError as exc:
        raise ValueError("stored roles are invalid") from exc


def _user_from_row(row: tuple[Any, ...]) -> ConsoleUser:
    return ConsoleUser(
        user_id=_user_id(row[0]),
        roles=_deserialize_roles(row[1]),
        enabled=bool(row[2]),
        created_at=_finite_time(row[3], "created_at"),
        updated_at=_finite_time(row[4], "updated_at"),
    )


def _token_digest(token: object) -> bytes | None:
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        return None
    try:
        raw = base64.urlsafe_b64decode(token + "=")
    except (ValueError, binascii.Error):
        return None
    if len(raw) != 32 or _b64encode(raw) != token:
        return None
    return hashlib.sha256(raw).digest()


class PostgresConsoleAuthStore:
    """Persist console accounts and revocable sessions using a caller connection.

    The connection must be dedicated to this store's coordinated transaction and
    not shared with unrelated work. A failure after database work begins rolls
    back the entire active transaction, even with ``commit=False``; callers must
    propagate the failure and abandon the unit of work. ``commit=False`` defers
    only a successful commit; it is not a savepoint or error isolation.
    """

    def __init__(
        self, connection: _Connection, prefix: str = "console_auth", *, schema: str = "public"
    ) -> None:
        """Wrap a DB-API connection and validate all interpolated SQL identifiers."""
        if not isinstance(prefix, str) or not _IDENTIFIER.fullmatch(prefix) or len(prefix) > 53:
            raise ValueError("prefix must be a safe SQL identifier of at most 53 characters")
        if not isinstance(schema, str) or not _IDENTIFIER.fullmatch(schema) or len(schema) > 63:
            raise ValueError("schema must be a safe SQL identifier of at most 63 characters")
        self._connection = connection
        self.prefix = prefix
        self.schema = schema
        qualified_schema = f'"{schema}"'
        self.users_table = f'{qualified_schema}."{prefix}_users"'
        self.sessions_table = f'{qualified_schema}."{prefix}_sessions"'
        self.bootstrap_table = f'{qualified_schema}."{prefix}_bootstrap"'

    @property
    def connection(self) -> _Connection:
        """Expose the injected connection for shared-transaction coordination."""
        return self._connection

    def ensure_schema(self) -> None:
        """Create account/session tables and their singleton bootstrap row."""
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {self.users_table} ("
                "user_id TEXT PRIMARY KEY, "
                "password_verifier TEXT NOT NULL, "
                "roles_json TEXT NOT NULL, "
                "enabled BOOLEAN NOT NULL, "
                "created_at DOUBLE PRECISION NOT NULL CHECK ("
                "created_at > '-Infinity'::DOUBLE PRECISION AND "
                "created_at < 'Infinity'::DOUBLE PRECISION), "
                "updated_at DOUBLE PRECISION NOT NULL CHECK ("
                "updated_at > '-Infinity'::DOUBLE PRECISION AND "
                "updated_at < 'Infinity'::DOUBLE PRECISION))"
            )
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {self.sessions_table} ("
                "token_digest BYTEA PRIMARY KEY CHECK (octet_length(token_digest) = 32), "
                "csrf_digest BYTEA NOT NULL CHECK (octet_length(csrf_digest) = 32), "
                f"user_id TEXT NOT NULL REFERENCES {self.users_table} (user_id), "
                "created_at DOUBLE PRECISION NOT NULL CHECK ("
                "created_at > '-Infinity'::DOUBLE PRECISION AND "
                "created_at < 'Infinity'::DOUBLE PRECISION), "
                "expires_at DOUBLE PRECISION NOT NULL CHECK ("
                "expires_at > created_at AND expires_at < 'Infinity'::DOUBLE PRECISION), "
                "revoked_at DOUBLE PRECISION CHECK (revoked_at IS NULL OR ("
                "revoked_at > '-Infinity'::DOUBLE PRECISION AND "
                "revoked_at < 'Infinity'::DOUBLE PRECISION)))"
            )
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {self.bootstrap_table} ("
                "singleton BOOLEAN PRIMARY KEY CHECK (singleton), "
                "complete BOOLEAN NOT NULL)"
            )
            cursor.execute(
                f"INSERT INTO {self.bootstrap_table} (singleton, complete) "
                "VALUES (TRUE, FALSE) ON CONFLICT (singleton) DO NOTHING"
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def bootstrap_admin(
        self, user_id: str, password: str, now: float, *, commit: bool = True
    ) -> ConsoleUser:
        """Atomically create the only first ADMIN, or refuse a repeated attempt.

        With ``commit=False``, success remains uncommitted; failures after
        database work begins roll back the entire active transaction.
        """
        user_id = _user_id(user_id)
        verifier = hash_password(password)
        timestamp = _finite_time(now, "now")
        roles_json = _serialize_roles((Role.ADMIN,))
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT complete FROM {self.bootstrap_table} WHERE singleton = TRUE FOR UPDATE"
            )
            guard = cursor.fetchone()
            if guard is None:
                raise BootstrapAlreadyCompleteError()
            cursor.execute(
                f"SELECT EXISTS (SELECT 1 FROM {self.users_table}), "
                f"EXISTS (SELECT 1 FROM {self.users_table} "
                "WHERE roles_json::jsonb @> '[\"admin\"]'::jsonb)"
            )
            existing = cursor.fetchone()
            if bool(guard[0]) or existing is None or bool(existing[0]) or bool(existing[1]):
                raise BootstrapAlreadyCompleteError()
            cursor.execute(
                f"INSERT INTO {self.users_table} "
                "(user_id, password_verifier, roles_json, enabled, created_at, updated_at) "
                "VALUES (%s, %s, %s, TRUE, %s, %s) ON CONFLICT (user_id) DO NOTHING "
                "RETURNING user_id",
                (user_id, verifier, roles_json, timestamp, timestamp),
            )
            if cursor.fetchone() is None:
                raise BootstrapAlreadyCompleteError()
            cursor.execute(
                f"UPDATE {self.bootstrap_table} SET complete = TRUE WHERE singleton = TRUE"
            )
            if commit:
                self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return ConsoleUser(user_id, frozenset({Role.ADMIN}), True, timestamp, timestamp)

    def create_user(
        self,
        user_id: str,
        password: str,
        roles: object,
        now: float,
        *,
        enabled: bool = True,
        commit: bool = True,
    ) -> ConsoleUser:
        """Create one account without retaining its plaintext password.

        With ``commit=False``, success remains uncommitted; failures after
        database work begins roll back the entire active transaction.
        """
        user_id = _user_id(user_id)
        verifier = hash_password(password)
        roles_json = _serialize_roles(roles)
        timestamp = _finite_time(now, "now")
        if type(enabled) is not bool:
            raise TypeError("enabled must be a boolean")
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT complete FROM {self.bootstrap_table} WHERE singleton = TRUE FOR UPDATE"
            )
            guard = cursor.fetchone()
            if guard is None:
                raise RuntimeError("console auth schema is not initialized")
            if not bool(guard[0]):
                raise ConsoleBootstrapRequiredError()
            cursor.execute(
                f"INSERT INTO {self.users_table} "
                "(user_id, password_verifier, roles_json, enabled, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING "
                "RETURNING user_id",
                (user_id, verifier, roles_json, enabled, timestamp, timestamp),
            )
            if cursor.fetchone() is None:
                raise DuplicateConsoleUserError()
            if commit:
                self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return ConsoleUser(user_id, _deserialize_roles(roles_json), enabled, timestamp, timestamp)

    def get_user(self, user_id: str) -> ConsoleUser | None:
        """Return one account without verifier material."""
        user_id = _user_id(user_id)
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT user_id, roles_json, enabled, created_at, updated_at "
            f"FROM {self.users_table} WHERE user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
        return None if row is None else _user_from_row(row)

    def list_users(self) -> tuple[ConsoleUser, ...]:
        """Return all accounts in stable user-id order."""
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT user_id, roles_json, enabled, created_at, updated_at "
            f"FROM {self.users_table} ORDER BY user_id"
        )
        return tuple(_user_from_row(row) for row in cursor.fetchall())

    def update_user(
        self,
        user_id: str,
        now: float,
        *,
        roles: object | None = None,
        password: str | None = None,
        enabled: bool | None = None,
        commit: bool = True,
    ) -> ConsoleUser:
        """Update account fields and revoke its sessions in the same transaction.

        With ``commit=False``, success remains uncommitted; failures after
        database work begins roll back the entire active transaction.
        """
        user_id = _user_id(user_id)
        timestamp = _finite_time(now, "now")
        if roles is None and password is None and enabled is None:
            raise ValueError("at least one account field must be updated")
        if enabled is not None and type(enabled) is not bool:
            raise TypeError("enabled must be a boolean")
        assignments: list[str] = []
        params: list[object] = []
        roles_json: str | None = None
        if roles is not None:
            roles_json = _serialize_roles(roles)
            assignments.append("roles_json = %s")
            params.append(roles_json)
        if password is not None:
            assignments.append("password_verifier = %s")
            params.append(hash_password(password))
        if enabled is not None:
            assignments.append("enabled = %s")
            params.append(enabled)
        assignments.append("updated_at = %s")
        params.extend((timestamp, user_id))
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT complete FROM {self.bootstrap_table} WHERE singleton = TRUE FOR UPDATE"
            )
            if cursor.fetchone() is None:
                raise RuntimeError("console auth schema is not initialized")
            cursor.execute(
                f"SELECT roles_json, enabled FROM {self.users_table} WHERE user_id = %s FOR UPDATE",
                (user_id,),
            )
            current = cursor.fetchone()
            if current is None:
                raise ConsoleUserNotFoundError()
            current_roles = _deserialize_roles(current[0])
            next_roles = current_roles if roles_json is None else _deserialize_roles(roles_json)
            next_enabled = bool(current[1]) if enabled is None else enabled
            if (
                bool(current[1])
                and Role.ADMIN in current_roles
                and (not next_enabled or Role.ADMIN not in next_roles)
            ):
                cursor.execute(
                    f"SELECT COUNT(*) FROM {self.users_table} WHERE enabled = TRUE "
                    "AND roles_json::jsonb @> '[\"admin\"]'::jsonb"
                )
                admin_count = cursor.fetchone()
                if admin_count is None or int(admin_count[0]) <= 1:
                    raise LastEnabledConsoleAdminError()
            cursor.execute(
                f"UPDATE {self.users_table} SET {', '.join(assignments)} "
                "WHERE user_id = %s RETURNING user_id",
                tuple(params),
            )
            if cursor.fetchone() is None:
                raise ConsoleUserNotFoundError()
            if roles is not None or password is not None or enabled is False:
                cursor.execute(
                    f"UPDATE {self.sessions_table} SET revoked_at = %s "
                    "WHERE user_id = %s AND revoked_at IS NULL",
                    (timestamp, user_id),
                )
            if commit:
                self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        updated = self.get_user(user_id)
        if updated is None:
            raise ConsoleUserNotFoundError()
        return updated

    def authenticate(self, user_id: str, password: str) -> Principal | None:
        """Verify credentials and hold the account lock through session creation."""
        try:
            password_bytes = _password_bytes(password)
        except _PasswordTooLongError:
            return None
        except (TypeError, ValueError):
            _verify_bytes("", _DUMMY_VERIFIER)
            return None
        try:
            normalized_id = _user_id(user_id)
        except (TypeError, ValueError):
            _verify_bytes(password, _DUMMY_VERIFIER)
            return None
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                f"SELECT password_verifier, roles_json, enabled FROM {self.users_table} "
                "WHERE user_id = %s FOR UPDATE",
                (normalized_id,),
            )
            row = cursor.fetchone()
            if row is None:
                self._connection.rollback()
                _verify_bytes(password, _DUMMY_VERIFIER)
                return None
            verifier = row[0]
            valid = _verify_bytes(password, verifier)
            if not valid or not bool(row[2]):
                self._connection.rollback()
                return None
            roles = _deserialize_roles(row[1])
            iterations, _, _ = _decode_verifier(verifier)
            if iterations < _CURRENT_ITERATIONS:
                replacement = _hash_bytes(password_bytes)
                cursor.execute(
                    f"UPDATE {self.users_table} SET password_verifier = %s "
                    "WHERE user_id = %s AND password_verifier = %s RETURNING user_id",
                    (replacement, normalized_id, verifier),
                )
                if cursor.fetchone() is None:
                    self._connection.rollback()
                    return None
            return Principal(normalized_id, roles)
        except Exception:
            self._connection.rollback()
            raise

    def create_session(
        self,
        user_id: str,
        now: float,
        ttl_seconds: int = _DEFAULT_SESSION_TTL_SECONDS,
        *,
        commit: bool = True,
    ) -> IssuedSession:
        """Issue tokens while persisting only SHA-256 digests.

        With ``commit=False``, success remains uncommitted; failures after
        database work begins roll back the entire active transaction.
        """
        user_id = _user_id(user_id)
        timestamp = _finite_time(now, "now")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= _MAX_SESSION_TTL_SECONDS:
            raise ValueError("ttl_seconds must be between 1 and 28800")
        expires_at = timestamp + ttl_seconds
        if not math.isfinite(expires_at):
            raise ValueError("session expiry must be finite")
        token_bytes = secrets.token_bytes(32)
        csrf_bytes = secrets.token_bytes(32)
        token = _b64encode(token_bytes)
        csrf_token = _b64encode(csrf_bytes)
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT enabled FROM {self.users_table} WHERE user_id = %s FOR SHARE",
                (user_id,),
            )
            user = cursor.fetchone()
            if user is None or not bool(user[0]):
                raise ConsoleUserNotFoundError()
            cursor.execute(
                f"INSERT INTO {self.sessions_table} "
                "(token_digest, csrf_digest, user_id, created_at, expires_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    hashlib.sha256(token_bytes).digest(),
                    hashlib.sha256(csrf_bytes).digest(),
                    user_id,
                    timestamp,
                    expires_at,
                ),
            )
            if commit:
                self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return IssuedSession(token, csrf_token, timestamp, expires_at)

    def resolve_session(self, token: str, now: float) -> Principal | None:
        """Resolve active session identity and current roles on every call."""
        timestamp = _finite_time(now, "now")
        digest = _token_digest(token)
        if digest is None:
            return None
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT u.user_id, u.roles_json FROM {self.sessions_table} s "
            f"JOIN {self.users_table} u ON u.user_id = s.user_id "
            "WHERE s.token_digest = %s AND s.revoked_at IS NULL "
            "AND s.expires_at > %s AND u.enabled = TRUE",
            (digest, timestamp),
        )
        row = cursor.fetchone()
        return None if row is None else Principal(_user_id(row[0]), _deserialize_roles(row[1]))

    def verify_csrf(self, token: str, csrf_cookie: str, header: str, now: float) -> bool:
        """Require an active session and constant-time agreement with its CSRF digest."""
        timestamp = _finite_time(now, "now")
        session_digest = _token_digest(token)
        cookie_digest = _token_digest(csrf_cookie)
        header_digest = _token_digest(header)
        if session_digest is None or cookie_digest is None or header_digest is None:
            return False
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT s.csrf_digest FROM {self.sessions_table} s "
            f"JOIN {self.users_table} u ON u.user_id = s.user_id "
            "WHERE s.token_digest = %s AND s.revoked_at IS NULL "
            "AND s.expires_at > %s AND u.enabled = TRUE",
            (session_digest, timestamp),
        )
        row = cursor.fetchone()
        if row is None:
            return False
        expected = bytes(row[0])
        return (
            hmac.compare_digest(expected, cookie_digest)
            and hmac.compare_digest(expected, header_digest)
            and hmac.compare_digest(csrf_cookie.encode("ascii"), header.encode("ascii"))
        )

    def revoke_user_sessions(self, user_id: str, now: float, *, commit: bool = True) -> int:
        """Revoke all active sessions for one account.

        With ``commit=False``, success remains uncommitted; failures after
        database work begins roll back the entire active transaction.
        """
        user_id = _user_id(user_id)
        timestamp = _finite_time(now, "now")
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"UPDATE {self.sessions_table} SET revoked_at = %s "
                "WHERE user_id = %s AND revoked_at IS NULL RETURNING token_digest",
                (timestamp, user_id),
            )
            revoked = len(cursor.fetchall())
            if commit:
                self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return revoked

    def revoke_session(self, token: str, now: float, *, commit: bool = True) -> bool:
        """Revoke only the session identified by ``token``.

        With ``commit=False``, success remains uncommitted; failures after
        database work begins roll back the entire active transaction.
        """
        timestamp = _finite_time(now, "now")
        digest = _token_digest(token)
        if digest is None:
            return False
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                f"UPDATE {self.sessions_table} SET revoked_at = %s "
                "WHERE token_digest = %s AND revoked_at IS NULL "
                "RETURNING token_digest",
                (timestamp, digest),
            )
            revoked = cursor.fetchone() is not None
            if commit:
                self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return revoked


def _verify_bytes(password: str, verifier: object) -> bool:
    password_bytes = _password_bytes(password)
    iterations, salt, expected = _decode_verifier(verifier)
    actual = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, iterations, dklen=_KEY_BYTES)
    return hmac.compare_digest(actual, expected)


def _hash_bytes(password_bytes: bytes) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password_bytes, salt, _CURRENT_ITERATIONS, dklen=_KEY_BYTES
    )
    return (
        f"pbkdf2-sha256$v1${_CURRENT_ITERATIONS}${_KEY_BYTES}$"
        f"{_b64encode(salt)}${_b64encode(digest)}"
    )
