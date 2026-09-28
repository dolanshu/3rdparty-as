"""Feature capability gating: the two-layer switch evaluation entry point.

Layer ① is the deployment-wide switch, layer ② the fine-grained runtime
override (ADR-0020, hld.md §7). M2 lands the seam only: the storage and hot
reload of layer ① belong to the control plane in M4.

Two properties are non-negotiable:

* **Fail-closed.** An unregistered name evaluates to ``False``. A switch that
  was never reviewed must not become a hole that lets traffic through
  (ADR-0020, REQ-G-1).
* **Idempotent.** The same scope evaluates to the same answer, so a split-brain
  window cannot flip a decision back and forth (risk R5, open item D3).

``is_enabled`` is pure: it reads no Redis, no clock and no global state. Every
value comes from the injected ``ToggleSource``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToggleScope:
    """The scope a switch is evaluated in (ADR-0020 layer ② granularity).

    Attributes:
        case: The use case, for example ``translation``.
        number: The number or number range the call belongs to.
        call_id: The Call-ID, the finest granularity.
    """

    case: str
    number: str = ""
    call_id: str = ""

    def scope_key(self) -> str:
        """Return the lookup key of this scope for runtime overrides.

        Returns:
            The scope rendered as ``case:number:call_id``.
        """
        return f"{self.case}:{self.number}:{self.call_id}"


class ToggleSource(Protocol):
    """Where switch values come from; the control plane supplies a real one."""

    def deployment_value(self, name: str) -> bool | None:
        """Return the layer ① value of a switch, or ``None`` when unset.

        Args:
            name: The switch name.
        """
        ...

    def runtime_override(self, name: str, scope: ToggleScope) -> bool | None:
        """Return the layer ② value for a scope, or ``None`` when unset.

        Args:
            name: The switch name.
            scope: The scope being evaluated.
        """
        ...


@dataclass(frozen=True)
class StaticToggleSource:
    """The default source: fixed values, no Redis, no clock.

    Attributes:
        deployment: Layer ① values keyed by switch name.
        overrides: Layer ② values keyed by ``(name, scope_key)``.
    """

    deployment: Mapping[str, bool] = field(default_factory=dict)
    overrides: Mapping[tuple[str, str], bool] = field(default_factory=dict)

    def deployment_value(self, name: str) -> bool | None:
        """Return the layer ① value of a switch, or ``None`` when unset.

        Args:
            name: The switch name.

        Returns:
            The configured value, or ``None``.
        """
        return self.deployment.get(name)

    def runtime_override(self, name: str, scope: ToggleScope) -> bool | None:
        """Return the layer ② value for a scope, or ``None`` when unset.

        Args:
            name: The switch name.
            scope: The scope being evaluated.

        Returns:
            The configured override, or ``None``.
        """
        return self.overrides.get((name, scope.scope_key()))


def is_enabled(name: str, scope: ToggleScope, source: ToggleSource) -> bool:
    """Evaluate one switch in one scope.

    The runtime override wins over the deployment level; anything unknown is
    off.

    Args:
        name: The switch name.
        scope: The scope being evaluated.
        source: Where the values come from.

    Returns:
        ``True`` only when a source explicitly enables the switch.
    """
    override = source.runtime_override(name, scope)
    if override is not None:
        return override  # layer ② outranks layer ①. See ADR-0020

    deployment_value = source.deployment_value(name)
    if deployment_value is not None:
        return deployment_value

    return False  # fail-closed: an unregistered switch is off. See ADR-0020
