"""The decision package: the pure routing policy of the kernel.

See ADR-0002 (one process per use case, kernel stays pure) and lld.md §2, §3.
"""

from __future__ import annotations

from .decide import (
    REASON_MATCH_BLOCK,
    REASON_MATCH_FORWARD,
    REASON_MATCH_TRANSLATE,
    REASON_NO_MATCH,
    Decision,
    DecisionAction,
    DecisionRequest,
    decide,
)
from .rules import Action, Rule, RuleSet, normalize_number

__all__: list[str] = [
    "REASON_MATCH_BLOCK",
    "REASON_MATCH_FORWARD",
    "REASON_MATCH_TRANSLATE",
    "REASON_NO_MATCH",
    "Action",
    "Decision",
    "DecisionAction",
    "DecisionRequest",
    "Rule",
    "RuleSet",
    "decide",
    "normalize_number",
]
