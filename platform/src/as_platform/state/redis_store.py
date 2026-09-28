"""Redis-backed StateStore: the production implementation of the seam.

Runtime state lives in Redis (+ Sentinel) so the process stays stateless. Keys
are namespaced ``as:{case}:{kind}:{id}`` and carry a TTL (ADR-0007); writes are
idempotent so a split-brain window can replay them (risk R5, open item D3).

**The client library is a declared runtime dependency** (``redis>=5.0``, see
ADR-0002 / ADR-0007). ``import redis`` still happens inside
:meth:`RedisStateStore.from_url` only, so importing the kernel never opens —
or requires — a connection.

The client is duck-typed: any object exposing ``get`` / ``set`` / ``setex`` /
``delete`` / ``expire`` works, which is what lets the contract test replay the
cases without a server.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from .store import KEY_PREFIX, build_key


@runtime_checkable
class RedisClient(Protocol):
    """The client surface the store uses; satisfied by ``redis.Redis``."""

    def get(self, key: str) -> bytes | str | None:
        """Read a key, returning ``None`` when absent.

        The result is ``bytes`` or ``str``: redis-py returns ``str`` when the
        client is built with ``decode_responses=True`` and ``bytes`` otherwise,
        so the protocol admits both. :class:`RedisStateStore` normalises the
        value to ``bytes`` before it leaves the store (see ADR-0007: runtime
        state is binary safe).
        """
        ...

    def set(self, key: str, value: bytes) -> object:
        """Write a key without a TTL."""
        ...

    def setex(self, key: str, ttl_seconds: int, value: bytes) -> object:
        """Write a key with a TTL."""
        ...

    def delete(self, key: str) -> object:
        """Remove a key."""
        ...

    def expire(self, key: str, ttl_seconds: int) -> object:
        """Re-arm the TTL of an existing key."""
        ...


class RedisStateStore:
    """A StateStore backed by Redis, with clock-injected expiry bookkeeping.

    The authoritative TTL lives on the server (``SETEX`` / ``EXPIRE``). The
    store also keeps a local expiry index so a read can refuse a key whose TTL
    has passed under the injected clock — that makes expiry deterministic in
    tests and harmless in production, where the server has already expired it.
    """

    def __init__(
        self,
        client: RedisClient,
        now: Callable[[], float],
        namespace: str = KEY_PREFIX,
    ) -> None:
        """Wrap an already connected client.

        Args:
            client: A connected client exposing the ``RedisClient`` surface.
            now: The injected clock, used for the local expiry index.
            namespace: The global key prefix, ``as`` by default.
        """
        self._client = client
        self._now = now
        self._namespace = namespace
        self._expires_at: dict[str, float] = {}

    @classmethod
    def from_url(cls, url: str, namespace: str, now: Callable[[], float]) -> RedisStateStore:
        """Connect to Redis and wrap the resulting client.

        Args:
            url: The connection URL, injected from configuration.
            namespace: The global key prefix.
            now: The injected clock, used for the local expiry index.

        Returns:
            A store over a freshly created client.
        """
        import redis  # lazy: the kernel does not hard-depend on the client

        return cls(client=redis.Redis.from_url(url), now=now, namespace=namespace)

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
        expires_at = self._expires_at.get(key)
        if expires_at is not None and self._now() >= expires_at:
            return None  # See ADR-0007: a runtime key past its TTL is gone

        raw = self._client.get(key)
        if isinstance(raw, str):
            return raw.encode("utf-8")
        return raw

    def set(self, key: str, value: bytes, ttl_seconds: float | None = None) -> None:
        """Write a key; writing the same value twice is idempotent.

        Args:
            key: A key built by ``build_key``.
            value: The bytes to store; values are binary safe.
            ttl_seconds: The lifetime of the key, or ``None`` for no expiry.
        """
        if ttl_seconds is None:
            self._expires_at.pop(key, None)
            self._client.set(key, value)
            return

        self._expires_at[key] = self._now() + ttl_seconds
        self._client.setex(key, int(ttl_seconds), value)  # See ADR-0007

    def delete(self, key: str) -> None:
        """Remove a key; deleting an absent key is not an error.

        Args:
            key: A key built by ``build_key``.
        """
        self._expires_at.pop(key, None)
        self._client.delete(key)

    def expire(self, key: str, ttl_seconds: float) -> None:
        """Re-arm the TTL of an existing key.

        Args:
            key: A key built by ``build_key``.
            ttl_seconds: The new lifetime, counted from the injected clock.
        """
        self._expires_at[key] = self._now() + ttl_seconds
        self._client.expire(key, int(ttl_seconds))
