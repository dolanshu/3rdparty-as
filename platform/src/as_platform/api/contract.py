"""Contract models of the internal API between the kernel and a use case process.

This module is **declaration only**: it fixes the wire shape the control plane
and the use case processes agree on, so both sides can be written and tested
against one contract. The transport and the serving side land in M4
(ADR-0002, lld.md §1).

The version travels with every bundle and every applied-version report: a
rolling distribution must be able to tell which version an instance is actually
running (ADR-0006, open item: version drift between PostgreSQL and the fleet).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# The wire version of this contract. Bump it whenever a model below changes.
INTERNAL_API_VERSION = "0.1.0"


@dataclass(frozen=True)
class RuleDTO:
    """One routing rule as it crosses the internal API.

    Attributes:
        rule_id: Stable identifier of the rule.
        prefix: The normalized number prefix the rule matches.
        action: The action name: ``forward``, ``translate`` or ``block``.
        target: Where to route the call; ``None`` when the action has none.
    """

    rule_id: str
    prefix: str
    action: str
    target: str | None = None


@dataclass(frozen=True)
class ToggleDTO:
    """One feature switch as it crosses the internal API.

    A switch is a versioned piece of configuration, not a code path: it is
    declared, reviewed, stored, distributed and rolled back by the same pipeline
    as a rule, so there is one staged path and not one per kind of
    configuration (ADR-0020, ADR-0006). Declaring one therefore carries the
    obligations AGENT.md §3.4 lists, which the fields below answer: the default
    state, the grey-release scope and the way out.

    Attributes:
        name: Stable identifier of the switch, for example ``translation.v2``.
        enabled: The layer ① value this version gives the switch. The **default
            state is off**: a switch is turned on by a reviewed change, and a
            name that appears in no version at all is off as well (fail-closed,
            the same answer ``as_platform.gating.is_enabled`` gives for it).
        removal_condition: When the switch is deleted. A switch without a way
            out is switch debt: it is never removed, and both of its states end
            up permanently untested. It is mandatory — deliberately not
            defaulted — for exactly that reason (ADR-0020, AGENT.md §3.4).
        scope: The scope this value applies to; ``""`` is the deployment-wide
            value (ADR-0020 layer ①).
    """

    name: str
    enabled: bool
    removal_condition: str
    scope: str = ""


@dataclass(frozen=True)
class ConfigBundle:
    """A configuration version handed to a use case process.

    A switch belongs to the same version as a rule: one version of the
    configuration carries both, and both travel the same governance pipeline —
    change order, approval, version repository, staged distribution, rollback
    (ADR-0020, ADR-0006).

    Attributes:
        version: The version of this bundle.
        rules: The rules of this version, in configuration order.
        toggles: The switches of this version, in configuration order. Empty
            means this version declares no switch, which is what every version
            written before a switch existed looks like; the default keeps such a
            bundle constructible. A switch this version does not declare is off
            (fail-closed), so an absent switch is never an enabled one.
    """

    version: str
    rules: tuple[RuleDTO, ...]
    toggles: tuple[ToggleDTO, ...] = ()


def toggle_deployment(config: ConfigBundle) -> Mapping[str, bool]:
    """Fold the switches of one configuration version into a deployment table.

    The result is the layer ① input of ``as_platform.gating.is_enabled``: one
    value per switch name and nothing else. Both states are kept — a switch this
    version turns off is folded in as ``False``, because dropping it would let
    the caller read the absence as "not configured yet" and, worse, let an older
    value survive a rollback. Only a name this version does not declare is
    absent, and that absence is read as off (fail-closed, ADR-0020).

    Args:
        config: The configuration version to fold.

    Returns:
        The switch name to the value this version gives it, holding both
        ``True`` and ``False`` entries.
    """
    return {toggle.name: toggle.enabled for toggle in config.toggles}


@dataclass(frozen=True)
class AppliedVersionReport:
    """What an instance reports back after loading a version.

    Attributes:
        case: The use case reporting, for example ``translation``.
        version: The configuration version now loaded.
        applied_at: When the version was applied, injected by the caller.
    """

    case: str
    version: str
    applied_at: float
