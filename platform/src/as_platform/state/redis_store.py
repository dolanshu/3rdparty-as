"""Redis-backed StateStore: the production implementation of the seam.

Runtime state lives in Redis (+ Sentinel) so the process stays stateless. Keys
are namespaced ``as:{case}:{kind}:{id}`` and carry a TTL (ADR-0007); writes are
idempotent so a split-brain window can replay them (risk R5, open item D3).

**The client library is a declared runtime dependency** (``redis>=5.0``, see
ADR-0002 / ADR-0007). ``import redis`` still happens inside factory methods
only, so importing the kernel never opens — or requires — a connection.

The client is duck-typed: any object exposing ``get`` / ``set`` / ``setex`` /
``delete`` / ``expire`` works, which is what lets the contract test replay the
cases without a server.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import Protocol, cast, runtime_checkable
from urllib.parse import unquote, urlparse

from .store import KEY_PREFIX, build_key

_DEFAULT_SENTINEL_PORT = 26379


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


def _parse_host_port(entry: str, default_port: int) -> tuple[str, int]:
    text = entry.strip()
    if not text:
        raise ValueError("sentinel host entry must be non-empty")
    if text.startswith("["):
        end = text.find("]")
        if end < 0:
            raise ValueError(f"invalid bracketed sentinel host: {entry!r}")
        host = text[1:end]
        rest = text[end + 1 :]
        if rest.startswith(":"):
            return host, int(rest[1:])
        return host, default_port
    if ":" in text:
        host, port_text = text.rsplit(":", 1)
        return host, int(port_text)
    return text, default_port


def parse_sentinel_hosts(hosts: str) -> list[tuple[str, int]]:
    """Parse comma-separated ``host:port`` sentinel endpoints."""
    entries = [part for part in hosts.split(",") if part.strip()]
    if not entries:
        raise ValueError("sentinel hosts must list at least one endpoint")
    return [_parse_host_port(entry, _DEFAULT_SENTINEL_PORT) for entry in entries]


def _parse_sentinel_url(url: str) -> tuple[list[tuple[str, int]], str, int]:
    """Parse ``redis+sentinel://host:port[,host:port]/master_name[/db]``."""
    parsed = urlparse(url)
    if parsed.scheme != "redis+sentinel":
        raise ValueError(f"unsupported redis URL scheme: {parsed.scheme}")
    hosts_part = parsed.netloc
    if not hosts_part:
        raise ValueError("redis+sentinel URL requires sentinel host(s) in the authority")
    path = parsed.path.lstrip("/")
    if not path:
        raise ValueError("redis+sentinel URL requires a master name in the path")
    segments = path.split("/")
    master_name = unquote(segments[0])
    if not master_name:
        raise ValueError("redis+sentinel URL master name must be non-empty")
    db = 0
    if len(segments) > 1 and segments[1]:
        db = int(segments[1])
    sentinel_hosts = parse_sentinel_hosts(hosts_part)
    return sentinel_hosts, master_name, db


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

        Supports direct ``redis://`` URLs and ``redis+sentinel://`` URLs.

        Args:
            url: The connection URL, injected from configuration.
            namespace: The global key prefix.
            now: The injected clock, used for the local expiry index.

        Returns:
            A store over a freshly created client.
        """
        if url.startswith("redis+sentinel://"):
            hosts, master_name, db = _parse_sentinel_url(url)
            return cls.from_sentinel(hosts, master_name, namespace, now, db=db)
        import redis  # lazy: the kernel does not hard-depend on the client

        return cls(client=redis.Redis.from_url(url), now=now, namespace=namespace)

    @classmethod
    def from_sentinel(
        cls,
        sentinel_hosts: str | Sequence[tuple[str, int]],
        master_name: str,
        namespace: str,
        now: Callable[[], float],
        *,
        db: int = 0,
        **redis_kwargs: object,
    ) -> RedisStateStore:
        """Connect via Redis Sentinel and wrap the master client.

        Args:
            sentinel_hosts: Comma-separated ``host:port`` list or an explicit
                sequence of ``(host, port)`` tuples.
            master_name: Sentinel service name for the Redis master.
            namespace: The global key prefix.
            now: The injected clock, used for the local expiry index.
            db: Logical Redis database index on the master.
            redis_kwargs: Forwarded to ``Sentinel.master_for`` (for example
                ``socket_timeout``).

        Returns:
            A store over a Sentinel-managed master client.
        """
        from redis.sentinel import Sentinel  # lazy: pulls in redis client package

        if isinstance(sentinel_hosts, str):
            endpoints = parse_sentinel_hosts(sentinel_hosts)
        else:
            endpoints = list(sentinel_hosts)
        if not master_name.strip():
            raise ValueError("master_name must be non-empty")
        sentinel = Sentinel(endpoints, **redis_kwargs)  # type: ignore[no-untyped-call]
        raw_client = sentinel.master_for(master_name, db=db)  # type: ignore[no-untyped-call]
        client = cast(RedisClient, raw_client)
        return cls(client=client, now=now, namespace=namespace)

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


def load_redis_store_from_env(
    now: Callable[[], float],
    namespace: str = KEY_PREFIX,
) -> RedisStateStore | None:
    """Build a :class:`RedisStateStore` from platform environment variables.

    Reads ``AS_REDIS_URL`` when set, otherwise the chart's ``REDIS_URL``.
    Otherwise uses ``AS_REDIS_SENTINEL_HOSTS`` and ``AS_REDIS_SENTINEL_MASTER``.
    Returns ``None`` when neither path is configured.
    """
    url = os.environ.get("AS_REDIS_URL", "").strip() or os.environ.get("REDIS_URL", "").strip()
    if url:
        return RedisStateStore.from_url(url, namespace, now)
    hosts = os.environ.get("AS_REDIS_SENTINEL_HOSTS", "").strip()
    master = os.environ.get("AS_REDIS_SENTINEL_MASTER", "").strip()
    if hosts and master:
        return RedisStateStore.from_sentinel(hosts, master, namespace, now)
    if hosts or master:
        raise ValueError("AS_REDIS_SENTINEL_HOSTS and AS_REDIS_SENTINEL_MASTER must both be set")
    return None
