"""Capacity harness (layer ⑥, performance).

Drives the AS over real sockets, never by calling callbacks directly: a harness
that bypasses the socket and the event loop measures business logic, not system
capacity. The numbers it produces are evidence for ADR-0011, not marketing.
"""

__all__: list[str] = []
