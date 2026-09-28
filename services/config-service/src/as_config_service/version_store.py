"""The configuration version repository: immutable version rows, append only.

ADR-0006 makes every configuration an immutable row in PostgreSQL: a new version
is appended, an old version is never updated, overwritten or deleted, and diff
and rollback are both computed from those rows. ADR-0007 assigns governance data
to PostgreSQL and runtime state to Redis, so this repository is the governance
side.

The production implementation is **PostgreSQL** and is deliberately not written
here: this milestone lands the pure logic kernel, and a repository that opens a
socket cannot be tested the way AGENT.md §5 demands. What lands instead is the
seam (`VersionStore`) plus an in-memory implementation for local runs and tests.
The PostgreSQL implementation is a drop-in replacement behind the same Protocol;
see ADR-0006 and ADR-0007.

Purity: no clock is read and no socket is opened here. Time is injected by the
caller, so a version's timestamp is a fact the caller owns, not something the
repository invents (AGENT.md §5).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from as_platform.api.contract import ConfigBundle


@dataclass(frozen=True)
class ConfigVersion:
    """One immutable version row of the configuration. See ADR-0006.

    Attributes:
        version: The version number, from 1 and strictly increasing.
        bundle: The configuration of this version.
        created_at: When the row was written, **injected by the caller**.
        change_id: The change order that produced this version; ``None`` only
            for versions written outside a change order, which ADR-0006 forbids
            in production. REQ-NF-10 (traceable).
    """

    version: int
    bundle: ConfigBundle
    created_at: float
    change_id: str | None = None


class VersionStore(Protocol):
    """Where configuration versions live. Implementations must be swappable.

    The production implementation is PostgreSQL (ADR-0006, ADR-0007); the
    in-memory one is for local runs and tests.
    """

    def append(
        self,
        bundle: ConfigBundle,
        now: float,
        change_id: str | None = None,
    ) -> ConfigVersion:
        """Append a version. The history already written is never modified.

        Args:
            bundle: The configuration to store as the new version.
            now: When the row is written, injected by the caller.
            change_id: The change order that produced this version.

        Returns:
            The appended version, numbered one higher than the previous head.
        """
        ...

    def latest(self) -> ConfigVersion | None:
        """The newest version.

        Returns:
            The last appended version, or ``None`` when nothing was appended.
        """
        ...

    def get(self, version: int) -> ConfigVersion | None:
        """Read one version out of history.

        Args:
            version: The version number to read.

        Returns:
            The version, or ``None`` when it was never written.
        """
        ...

    def history(self) -> tuple[ConfigVersion, ...]:
        """The whole history, oldest first.

        Returns:
            Every version ever appended, in append order.
        """
        ...


class InMemoryVersionStore:
    """A process-local version repository for local runs and tests.

    PostgreSQL replaces it in production (ADR-0006, ADR-0007). The semantics it
    pins are the ones the PostgreSQL implementation must reproduce: append-only,
    numbered from one, history readable forever.

    Attributes:
        now: The injected clock. It supplies ``created_at`` when the caller does
            not pass one to ``append``; the repository itself never reads the
            system clock (AGENT.md §5).
    """

    def __init__(self, now: Callable[[], float]) -> None:
        """Create an empty repository.

        Args:
            now: The injected clock, returning seconds.
        """
        self._now = now
        self._versions: list[ConfigVersion] = []

    def append(
        self,
        bundle: ConfigBundle,
        now: float | None = None,
        change_id: str | None = None,
    ) -> ConfigVersion:
        """Append a version, leaving every existing row untouched. See ADR-0006.

        Args:
            bundle: The configuration to store as the new version.
            now: When the row is written, injected by the caller. ``None`` falls
                back to the clock this store was built with.
            change_id: The change order that produced this version.

        Returns:
            The appended version, whose number is one higher than the previous
            head, or 1 for the first append.
        """
        created_at = self._now() if now is None else now
        version = ConfigVersion(
            version=len(self._versions) + 1,
            bundle=bundle,
            created_at=created_at,
            change_id=change_id,
        )
        self._versions.append(version)
        return version

    def latest(self) -> ConfigVersion | None:
        """The newest version.

        Returns:
            The last appended version, or ``None`` when nothing was appended.
        """
        if not self._versions:
            return None
        return self._versions[-1]

    def get(self, version: int) -> ConfigVersion | None:
        """Read one version out of history.

        Args:
            version: The version number to read.

        Returns:
            The version, or ``None`` when it was never written.
        """
        for stored in self._versions:
            if stored.version == version:
                return stored
        return None

    def history(self) -> tuple[ConfigVersion, ...]:
        """The whole history, oldest first.

        Returns:
            Every version appended so far, in append order.
        """
        return tuple(self._versions)
