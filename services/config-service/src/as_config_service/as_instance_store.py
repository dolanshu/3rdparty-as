"""PostgreSQL inventory for fleet AS instances. REQ-F-15 / M4b-7.5."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

from as_config_service.as_instance import AsInstance, AsUseCase

_IDENTIFIER = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
_INSTANCE_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.@-]{0,255}\Z")
_MAX_SCHEMA_LENGTH = 63
_REJECTED_CATEGORIES = {"Cc", "Cf", "Cs", "Zl", "Zp"}
_USE_CASES = frozenset({case.value for case in AsUseCase})


class DuplicateAsInstanceError(Exception):
    """Raised when an instance id is already registered."""


class AsInstanceNotFoundError(LookupError):
    """Raised when an instance id is not present."""


class StaleAsInstanceRevisionError(Exception):
    """Raised when an update or delete does not name the current revision."""

    def __init__(self, instance_id: str, expected_revision: int, actual_revision: int) -> None:
        """Record the compare-and-swap values for the caller."""
        super().__init__(
            f"stale as instance {instance_id!r}: expected revision {expected_revision}, "
            f"current revision is {actual_revision}"
        )
        self.instance_id = instance_id
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision


@dataclass(frozen=True)
class StoredAsInstance:
    """One inventory row with compare-and-swap revision metadata."""

    instance: AsInstance
    revision: int
    change_id: str
    actor: str
    updated_at: float


class _Cursor(Protocol):
    def execute(self, sql: str, params: tuple[object, ...] = ()) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...


class _Connection(Protocol):
    info: Any

    def cursor(self) -> _Cursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class AsInstanceStore(Protocol):
    """Repository operations for fleet instance inventory."""

    def create(
        self,
        instance: AsInstance,
        change_id: str,
        actor: str,
        updated_at: float,
        *,
        commit: bool = True,
    ) -> StoredAsInstance:
        """Insert a new instance at revision one."""
        ...

    def get(self, instance_id: str) -> StoredAsInstance | None:
        """Return the current row for an instance id, if present."""
        ...

    def list_all(self) -> tuple[StoredAsInstance, ...]:
        """Return every instance ordered by id."""
        ...

    def update(
        self,
        instance: AsInstance,
        change_id: str,
        actor: str,
        updated_at: float,
        expected_revision: int,
        *,
        commit: bool = True,
    ) -> StoredAsInstance:
        """Replace a row when the expected revision matches."""
        ...

    def delete(
        self,
        instance_id: str,
        change_id: str,
        actor: str,
        updated_at: float,
        expected_revision: int,
        *,
        commit: bool = True,
    ) -> None:
        """Remove an instance when the expected revision matches."""
        ...


class PostgresAsInstanceStore:
    """Mutable inventory rows with revision compare-and-swap on the injected connection."""

    def __init__(
        self, connection: _Connection, prefix: str = "as_instances", *, schema: str = "public"
    ) -> None:
        """Wrap an open DB-API connection and validate interpolated SQL names."""
        if not isinstance(prefix, str) or not _IDENTIFIER.fullmatch(prefix) or len(prefix) > 56:
            raise ValueError("prefix must be a safe SQL identifier of at most 56 characters")
        if (
            not isinstance(schema, str)
            or not _IDENTIFIER.fullmatch(schema)
            or len(schema) > _MAX_SCHEMA_LENGTH
        ):
            raise ValueError("schema must be a safe SQL identifier of at most 63 characters")
        self._connection = connection
        self.schema = schema
        qualified_schema = f'"{schema}"'
        self.table = f'{qualified_schema}."{prefix}"'

    @property
    def connection(self) -> _Connection:
        """Expose the injected connection for shared-transaction coordination."""
        return self._connection

    def ensure_schema(self) -> None:
        """Create the inventory table when missing; safe to repeat."""
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} ("
                "instance_id TEXT PRIMARY KEY, "
                "use_case TEXT NOT NULL, "
                "notify_url TEXT, "
                "health_url TEXT, "
                "enabled BOOLEAN NOT NULL, "
                "revision INTEGER NOT NULL CHECK (revision > 0), "
                "change_id TEXT NOT NULL CHECK (btrim(change_id) <> ''), "
                "actor TEXT NOT NULL CHECK (btrim(actor) <> ''), "
                "updated_at DOUBLE PRECISION NOT NULL CHECK ("
                "updated_at > '-Infinity'::DOUBLE PRECISION AND "
                "updated_at < 'Infinity'::DOUBLE PRECISION), "
                f"CHECK (use_case IN ({', '.join(repr(value) for value in sorted(_USE_CASES))}))"
                ")"
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def create(
        self,
        instance: AsInstance,
        change_id: str,
        actor: str,
        updated_at: float,
        *,
        commit: bool = True,
    ) -> StoredAsInstance:
        """Insert a new instance row at revision one."""
        try:
            _validate_row_input(instance, change_id, actor, updated_at)
            cursor = self._connection.cursor()
            cursor.execute(
                f"INSERT INTO {self.table} "
                "(instance_id, use_case, notify_url, health_url, enabled, revision, "
                "change_id, actor, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s) "
                "ON CONFLICT (instance_id) DO NOTHING RETURNING instance_id",
                (
                    instance.instance_id,
                    instance.use_case.value,
                    instance.notify_url,
                    instance.health_url,
                    instance.enabled,
                    change_id,
                    actor,
                    updated_at,
                ),
            )
            if cursor.fetchone() is None:
                raise DuplicateAsInstanceError(
                    f"as instance {instance.instance_id!r} already exists"
                )
            if commit:
                self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return StoredAsInstance(instance, 1, change_id, actor, updated_at)

    def get(self, instance_id: str) -> StoredAsInstance | None:
        """Return the current row for an instance id, if present."""
        _require_instance_id(instance_id)
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT instance_id, use_case, notify_url, health_url, enabled, revision, "
            f"change_id, actor, updated_at FROM {self.table} WHERE instance_id = %s",
            (instance_id,),
        )
        row = cursor.fetchone()
        return None if row is None else _stored_instance(row)

    def list_all(self) -> tuple[StoredAsInstance, ...]:
        """Return every instance ordered by id."""
        cursor = self._connection.cursor()
        cursor.execute(
            f"SELECT instance_id, use_case, notify_url, health_url, enabled, revision, "
            f"change_id, actor, updated_at FROM {self.table} ORDER BY instance_id ASC"
        )
        return tuple(_stored_instance(row) for row in cursor.fetchall())

    def update(
        self,
        instance: AsInstance,
        change_id: str,
        actor: str,
        updated_at: float,
        expected_revision: int,
        *,
        commit: bool = True,
    ) -> StoredAsInstance:
        """Replace a row when the expected revision matches."""
        try:
            if type(expected_revision) is not int or expected_revision < 1:
                raise ValueError("expected_revision must be a positive integer")
            _validate_row_input(instance, change_id, actor, updated_at)
            cursor = self._connection.cursor()
            cursor.execute(
                f"SELECT revision FROM {self.table} WHERE instance_id = %s FOR UPDATE",
                (instance.instance_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise AsInstanceNotFoundError(
                    f"as instance {instance.instance_id!r} does not exist"
                )
            actual_revision = int(row[0])
            if actual_revision != expected_revision:
                raise StaleAsInstanceRevisionError(
                    instance.instance_id, expected_revision, actual_revision
                )
            new_revision = actual_revision + 1
            cursor.execute(
                f"UPDATE {self.table} SET use_case = %s, notify_url = %s, health_url = %s, "
                "enabled = %s, revision = %s, change_id = %s, actor = %s, updated_at = %s "
                "WHERE instance_id = %s AND revision = %s RETURNING revision",
                (
                    instance.use_case.value,
                    instance.notify_url,
                    instance.health_url,
                    instance.enabled,
                    new_revision,
                    change_id,
                    actor,
                    updated_at,
                    instance.instance_id,
                    actual_revision,
                ),
            )
            if cursor.fetchone() is None:
                raise StaleAsInstanceRevisionError(
                    instance.instance_id, expected_revision, actual_revision
                )
            if commit:
                self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return StoredAsInstance(instance, new_revision, change_id, actor, updated_at)

    def delete(
        self,
        instance_id: str,
        change_id: str,
        actor: str,
        updated_at: float,
        expected_revision: int,
        *,
        commit: bool = True,
    ) -> None:
        """Remove an instance when the expected revision matches."""
        try:
            if type(expected_revision) is not int or expected_revision < 1:
                raise ValueError("expected_revision must be a positive integer")
            _require_instance_id(instance_id)
            _require_nonblank_text(change_id, "change_id")
            _require_nonblank_text(actor, "actor")
            _require_finite_number(updated_at, "updated_at")
            cursor = self._connection.cursor()
            cursor.execute(
                f"DELETE FROM {self.table} WHERE instance_id = %s AND revision = %s "
                "RETURNING instance_id",
                (instance_id, expected_revision),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"SELECT revision FROM {self.table} WHERE instance_id = %s",
                    (instance_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise AsInstanceNotFoundError(f"as instance {instance_id!r} does not exist")
                raise StaleAsInstanceRevisionError(instance_id, expected_revision, int(row[0]))
            if commit:
                self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise


def _stored_instance(row: tuple[Any, ...]) -> StoredAsInstance:
    (
        instance_id,
        use_case,
        notify_url,
        health_url,
        enabled,
        revision,
        change_id,
        actor,
        updated_at,
    ) = row
    return StoredAsInstance(
        instance=AsInstance(
            instance_id=instance_id,
            use_case=AsUseCase(use_case),
            notify_url=notify_url,
            health_url=health_url,
            enabled=bool(enabled),
        ),
        revision=int(revision),
        change_id=change_id,
        actor=actor,
        updated_at=float(updated_at),
    )


def _validate_row_input(
    instance: AsInstance, change_id: str, actor: str, updated_at: float
) -> None:
    if type(instance) is not AsInstance:
        raise TypeError("instance must be an AsInstance")
    _require_instance_id(instance.instance_id)
    if instance.use_case.value not in _USE_CASES:
        raise ValueError("use_case is invalid")
    _validate_optional_url(instance.notify_url, "notify_url")
    _validate_optional_url(instance.health_url, "health_url")
    if type(instance.enabled) is not bool:
        raise ValueError("enabled must be a bool")
    _require_nonblank_text(change_id, "change_id")
    _require_nonblank_text(actor, "actor")
    _require_finite_number(updated_at, "updated_at")


def _require_instance_id(value: str) -> None:
    if not isinstance(value, str) or not _INSTANCE_ID.fullmatch(value):
        raise ValueError("instance_id must be a safe, nonblank identifier")
    if any(unicodedata.category(character) in _REJECTED_CATEGORIES for character in value):
        raise ValueError("instance_id must not contain prohibited Unicode characters")


def _validate_optional_url(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or null")
    stripped = value.strip()
    if not stripped:
        return
    parsed = urlparse(stripped)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an http or https URL")


def _require_nonblank_text(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    if any(unicodedata.category(character) in _REJECTED_CATEGORIES for character in value):
        raise ValueError(f"{field_name} must not contain prohibited Unicode characters")


def _require_finite_number(value: object, field_name: str) -> None:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    if isinstance(value, int):
        number: int | float = int(value)
    elif isinstance(value, float):
        number = float(value)
    else:
        raise ValueError(f"{field_name} must be a finite number")
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
