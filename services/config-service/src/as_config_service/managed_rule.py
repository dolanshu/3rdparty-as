"""Immutable management-plane rule definitions for REQ-F-12.

Regex values remain declarative text: executable regex semantics and mapping to
the runtime rule schema are separate and are not implemented here.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum


class MatchField(Enum):
    """The address field a managed rule examines."""

    CALLING = "calling"
    CALLED = "called"


class MatchMode(Enum):
    """How a managed rule compares its match value."""

    PREFIX = "prefix"
    REGEX = "regex"


class TargetService(Enum):
    """The service selected by a managed rule."""

    TRANSLATION = "translation"
    ANTI_FRAUD = "anti-fraud"
    ROUTING = "routing"
    BLOCK = "block"
    DEFAULT = "default"


def _normalized_text(value: str, field_name: str, allow_empty: bool = False) -> str:
    """Validate untrusted rule text and return its trimmed canonical form."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    rejected_categories = {"Cc", "Cf", "Cs", "Zl", "Zp"}
    if any(unicodedata.category(character) in rejected_categories for character in value):
        raise ValueError(
            f"{field_name} must not contain control, format, surrogate, or "
            "line/paragraph separator characters"
        )

    normalized = value.strip()
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


@dataclass(frozen=True)
class ManagedRule:
    """One immutable rule definition managed by the control plane. REQ-F-12."""

    rule_id: str
    name: str
    match_field: MatchField
    match_mode: MatchMode
    match_value: str
    target_service: TargetService
    enabled: bool
    target_detail: str | None = None

    def __post_init__(self) -> None:
        """Canonicalize text and reject invalid values at the model boundary."""
        for field_name in ("rule_id", "name", "match_value"):
            object.__setattr__(
                self,
                field_name,
                _normalized_text(getattr(self, field_name), field_name),
            )

        if self.target_detail is not None:
            object.__setattr__(
                self,
                "target_detail",
                _normalized_text(self.target_detail, "target_detail", allow_empty=True),
            )

        if not isinstance(self.match_field, MatchField):
            raise TypeError("match_field must be a MatchField")
        if not isinstance(self.match_mode, MatchMode):
            raise TypeError("match_mode must be a MatchMode")
        if not isinstance(self.target_service, TargetService):
            raise TypeError("target_service must be a TargetService")
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be a bool")
