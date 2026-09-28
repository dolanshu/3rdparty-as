"""The state package: the StateStore seam and its implementations.

Runtime state (sessions, dialogs, rate windows) lives outside the process, so
the process itself stays stateless and restartable. See ADR-0002 and ADR-0007.
"""

from __future__ import annotations

from .in_memory import InMemoryStateStore
from .store import StateStore, build_key

__all__: list[str] = [
    "InMemoryStateStore",
    "StateStore",
    "build_key",
]
