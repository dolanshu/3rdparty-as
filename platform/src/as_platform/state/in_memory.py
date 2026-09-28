"""In-memory StateStore for tests and local development.

Expiry is decided by an **injected** clock, never by reading the system clock,
so TTL behaviour can be asserted deterministically. The same discipline that
makes ``decide()`` a pure function applies here. See ADR-0002, ADR-0007.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .store import KEY_PREFIX, build_key


@dataclass(frozen=True)
class _Entry:
    """One stored value plus its optional expiry timestamp."""

    value: bytes
    expires_at: float | None


class InMemoryStateStore:
    """A process-local StateStore with clock-injected TTLs.

    Attributes:
        now: The injected clock, called when a TTL is armed or checked.
        namespace: The global key prefix; ``as`` yields ADR-0007 keys.
    """

    def __init__(self, now: Callable[[], float], namespace: str = KEY_PREFIX) -> None:
        """Create an empty store.

        Args:
            now: The injected clock, returning seconds.
            namespace: The global key prefix, ``as`` by default.
        """
        self._now = now
        self._namespace = namespace
        self._entries: dict[str, _Entry] = {}

    def build_key(self, case: str, kind: str, entity_id: str) -> str:
        """Build a runtime key in this store's namespace.

        Args:
            case: The use case owning the key.
            kind: The kind of state.
            entity_id: The identifier, typically a Call-ID.

        Returns:
            The key ``as:{case}:{kind}:{id}``.
        """
        return build_key(case, kind, entity_id, self._namespace)

    def get(self, key: str) -> bytes | None:
        """Read a key, returning ``None`` when it is absent or expired.

        Args:
            key: A key built by ``build_key``.

        Returns:
            The stored bytes, or ``None``.
        """
        entry = self._entries.get(key)
        if entry is None:
            return None

        if entry.expires_at is not None and self._now() >= entry.expires_at:
            # Expired keys are dropped; a runtime key past its TTL is gone.
            # See ADR-0007.
            del self._entries[key]
            return None

        return entry.value

    def set(self, key: str, value: bytes, ttl_seconds: float | None = None) -> None:
        """Write a key; writing the same value twice is idempotent.

        Args:
            key: A key built by ``build_key``.
            value: The bytes to store.
            ttl_seconds: The lifetime of the key, or ``None`` for no expiry.
        """
        expires_at = None if ttl_seconds is None else self._now() + ttl_seconds
        self._entries[key] = _Entry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> None:
        """Remove a key; deleting an absent key does nothing.

        Args:
            key: A key built by ``build_key``.
        """
        self._entries.pop(key, None)

    def expire(self, key: str, ttl_seconds: float) -> None:
        """Re-arm the TTL of an existing key.

        Args:
            key: A key built by ``build_key``.
            ttl_seconds: The new lifetime, counted from the injected clock.
        """
        entry = self._entries.get(key)
        if entry is None:
            return

        self._entries[key] = _Entry(value=entry.value, expires_at=self._now() + ttl_seconds)
