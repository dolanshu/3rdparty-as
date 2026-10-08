"""Optional runtime probes for ops metrics (M5.1)."""

from __future__ import annotations


def probe_redis_available(url: str, *, timeout_seconds: float = 1.0) -> bool:
    """Return whether Redis answers ``PING`` within the timeout.

    Args:
        url: ``REDIS_URL`` from deployment configuration.
        timeout_seconds: Socket connect timeout for the probe.

    Returns:
        ``False`` when the URL is empty or the probe fails.
    """
    if not url.strip():
        return False
    try:
        import redis  # lazy: optional at import time

        client = redis.Redis.from_url(url, socket_connect_timeout=timeout_seconds)
        return client.ping() is True
    except Exception:
        return False
