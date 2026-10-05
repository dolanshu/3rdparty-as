"""Helpers for optional cmake-built native extensions in tests."""

from __future__ import annotations

import os

import pytest

from as_platform.sip.resip_runtime import load_resip_runtime_extension


def require_resip_runtime_extension() -> object:
    """Return ``_resip_runtime`` or skip/fail per ``AS_REQUIRE_NATIVE_EXTENSIONS``."""
    extension = load_resip_runtime_extension()
    if extension is not None:
        return extension
    message = "platform _resip_runtime extension not built; run make m2-platform-resip-build"
    if os.environ.get("AS_REQUIRE_NATIVE_EXTENSIONS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        pytest.fail(message)
    pytest.skip(message)
