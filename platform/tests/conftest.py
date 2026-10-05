"""Shared pytest hooks for platform tests."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_native_runtime: needs _resip_runtime (make m2-platform-resip-build)",
    )
