"""Load downscale-guard deployment settings from the environment (ADR-0010)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from as_platform.ops.downscale_guard import InstanceLoad, may_remove


@dataclass(frozen=True)
class DownscaleGuardConfig:
    """Runtime view of Helm ``downscaleGuard`` values exposed as env vars.

    Attributes:
        enabled: Whether the guard policy is active for this process.
        protect_when_active_calls_above: Instances with more than this many
            in-flight calls must not be selected for removal.
    """

    enabled: bool
    protect_when_active_calls_above: int


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean env value: {raw!r}")


def load_downscale_guard_config() -> DownscaleGuardConfig:
    """Read ``AS_DOWNSCALE_GUARD_*`` set by ``deploy/helm/templates/configmap.yaml``.

    Returns:
        Parsed configuration with safe defaults when variables are unset.
    """
    enabled = _parse_bool(os.environ.get("AS_DOWNSCALE_GUARD_ENABLED"), default=True)
    raw_threshold = os.environ.get("AS_DOWNSCALE_GUARD_PROTECT_ABOVE", "0")
    try:
        threshold = int(raw_threshold)
    except ValueError as error:
        raise ValueError("AS_DOWNSCALE_GUARD_PROTECT_ABOVE must be an integer") from error
    return DownscaleGuardConfig(enabled=enabled, protect_when_active_calls_above=threshold)


def pod_removable_under_guard(
    config: DownscaleGuardConfig,
    *,
    instance_id: str,
    active_calls: int,
    draining: bool,
) -> bool:
    """Whether this process may be selected for scale-down removal (ADR-0010).

    When the guard is disabled, only an instance already draining is blocked;
    active-call protection is not applied.
    """
    if not config.enabled:
        return not draining
    return may_remove(
        InstanceLoad(instance_id, active_calls, draining=draining),
        config.protect_when_active_calls_above,
    )
