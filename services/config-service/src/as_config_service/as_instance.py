"""Fleet AS instance inventory model for REQ-F-15 / M4b-7.5."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AsUseCase(str, Enum):
    """Supported AS deployment roles referenced by distribution batches."""

    TRANSLATION = "translation"
    ANTI_FRAUD = "anti-fraud"


@dataclass(frozen=True)
class AsInstance:
    """One registered AS instance and its outbound integration endpoints."""

    instance_id: str
    use_case: AsUseCase
    notify_url: str | None
    health_url: str | None
    enabled: bool
