"""Rule sets: number normalization and the winner selection of prefix matching.

Matching runs on the **called** number (REQ-F-6). Among all rules whose prefix
matches, the winner is chosen by ``(action_rank, prefix_length)`` descending:

* ``BLOCK`` (2) outranks ``TRANSLATE`` (1) outranks ``FORWARD`` (0), so a block
  always wins over a translate even when the translate prefix is longer. That
  ordering is required by REQ-F-7 and stated in docs/acceptance/test-plan.md
    §1.2 ("block rules > translation rules > default route"): refusing a call is the safe answer
  whenever a block rule is in play.
* Within one action, the longer prefix wins (longest-prefix-first, REQ-F-6).

Everything here is pure: no socket, no clock, no global state. See ADR-0002 and
AGENT.md §5.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Characters carriers and consoles put into numbers for readability. They carry
# no routing meaning, so they are dropped before matching.
_SEPARATORS: frozenset[str] = frozenset(" \t\r\n-()./")


class Action(Enum):
    """What a matched rule asks the kernel to do with the call."""

    FORWARD = "forward"
    TRANSLATE = "translate"
    BLOCK = "block"


# Blocking is the safest outcome, so it ranks highest. See REQ-F-7.
_ACTION_RANK: dict[Action, int] = {
    Action.BLOCK: 2,
    Action.TRANSLATE: 1,
    Action.FORWARD: 0,
}


def normalize_number(raw: str) -> str:
    """Normalize a phone number to its E.164-like comparison form.

    Whitespace and separator characters are removed and a missing leading ``+``
    is added, so ``867551234567`` and ``+86-755-1234-567`` compare equal.

    Args:
        raw: The number as it arrived, possibly carrying separators.

    Returns:
        The number with separators removed and a leading ``+``. An empty input
        yields an empty string.
    """
    body = "".join(character for character in raw.strip() if character not in _SEPARATORS)
    if not body:
        return ""

    digits = "".join(character for character in body if character.isdigit())
    return f"+{digits}"


@dataclass(frozen=True)
class Rule:
    """One routing rule.

    Attributes:
        rule_id: Stable identifier, reported back in ``Decision.matched_rule_id``.
        prefix: The number prefix this rule matches, in normalized form.
        action: What to do when this rule wins.
        target: Where to send the call; ``None`` means "no rewriting target".
    """

    rule_id: str
    prefix: str
    action: Action
    target: str | None = None


@dataclass(frozen=True)
class RuleSet:
    """An immutable collection of rules loaded from one configuration version."""

    rules: tuple[Rule, ...]

    def match(self, number: str) -> Rule | None:
        """Select the rule that governs a called number.

        Args:
            number: The called number, normalized before matching.

        Returns:
            The winning rule, or ``None`` when no prefix matches.
        """
        normalized = normalize_number(number)

        candidates = [
            (_ACTION_RANK[rule.action], len(normalize_number(rule.prefix)), rule)
            for rule in self.rules
            if normalized.startswith(normalize_number(rule.prefix))
        ]
        if not candidates:
            return None

        # Highest action rank first, then the longest prefix. An empty prefix
        # matches every number and therefore acts as a default route.
        winner = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
        return winner[2]
