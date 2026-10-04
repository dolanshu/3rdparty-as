"""Unit tests for downscale guard environment configuration."""

from __future__ import annotations

import pytest

from as_platform.ops.downscale_config import load_downscale_guard_config

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
