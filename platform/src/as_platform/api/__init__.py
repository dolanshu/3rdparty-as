"""The internal API package: the contract between the kernel and a use case.

The models here are the wire shape of the internal API. The implementation of
that API belongs to M4. See ADR-0002 and lld.md §1.
"""

from __future__ import annotations

from .contract import (
    AppliedVersionReport,
    ConfigBundle,
    RuleDTO,
    ToggleDTO,
    toggle_deployment,
)

__all__: list[str] = [
    "AppliedVersionReport",
    "ConfigBundle",
    "RuleDTO",
    "ToggleDTO",
    "toggle_deployment",
]
