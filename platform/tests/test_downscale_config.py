"""Unit tests for downscale guard environment configuration."""

from __future__ import annotations

import pytest

from as_platform.ops.downscale_config import (
    DownscaleGuardConfig,
    load_downscale_guard_config,
    pod_removable_under_guard,
)

pytestmark = pytest.mark.unit


def test_defaults_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AS_DOWNSCALE_GUARD_ENABLED", raising=False)
    monkeypatch.delenv("AS_DOWNSCALE_GUARD_PROTECT_ABOVE", raising=False)
    config = load_downscale_guard_config()
    assert config.enabled is True
    assert config.protect_when_active_calls_above == 0


def test_reads_explicit_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AS_DOWNSCALE_GUARD_ENABLED", "false")
    monkeypatch.setenv("AS_DOWNSCALE_GUARD_PROTECT_ABOVE", "2")
    config = load_downscale_guard_config()
    assert config.enabled is False
    assert config.protect_when_active_calls_above == 2


def test_invalid_enabled_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AS_DOWNSCALE_GUARD_ENABLED", "maybe")
    with pytest.raises(ValueError, match="invalid boolean"):
        load_downscale_guard_config()


def test_invalid_protect_above_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AS_DOWNSCALE_GUARD_PROTECT_ABOVE", "not-int")
    with pytest.raises(ValueError, match="must be an integer"):
        load_downscale_guard_config()


def test_guard_enabled_blocks_when_calls_exceed_threshold() -> None:
    config = DownscaleGuardConfig(enabled=True, protect_when_active_calls_above=0)
    assert (
        pod_removable_under_guard(
            config,
            instance_id="pod-a",
            active_calls=1,
            draining=False,
        )
        is False
    )


def test_guard_disabled_ignores_active_calls() -> None:
    config = DownscaleGuardConfig(enabled=False, protect_when_active_calls_above=0)
    assert (
        pod_removable_under_guard(
            config,
            instance_id="pod-a",
            active_calls=5,
            draining=False,
        )
        is True
    )


def test_guard_disabled_still_blocks_while_draining() -> None:
    config = DownscaleGuardConfig(enabled=False, protect_when_active_calls_above=0)
    assert (
        pod_removable_under_guard(
            config,
            instance_id="pod-a",
            active_calls=0,
            draining=True,
        )
        is False
    )
