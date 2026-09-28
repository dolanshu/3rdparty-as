"""Unit tests for number normalization and rule selection.

Acceptance: docs/acceptance/test-plan.md §1.2 (REQ-F-6 longest prefix, REQ-F-7
block outranks translate) and §5.1 (the decide() matrix).
"""

from __future__ import annotations

import pytest

from as_platform.decision.rules import Action, Rule, RuleSet, normalize_number

pytestmark = pytest.mark.unit


def _rule_set() -> RuleSet:
    """The four-rule fixture of test-plan §5.1."""
    return RuleSet(
        rules=(
            Rule(rule_id="rule-755", prefix="+86755", action=Action.TRANSLATE, target="return-uas"),
            Rule(
                rule_id="rule-75512",
                prefix="+8675512",
                action=Action.TRANSLATE,
                target="return-uas",
            ),
            Rule(rule_id="rule-138", prefix="+86138", action=Action.FORWARD),
            Rule(rule_id="rule-168", prefix="+86168", action=Action.BLOCK),
        )
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+867551234567", "+867551234567"),
        ("867551234567", "+867551234567"),
        (" +86 755 1234 567 ", "+867551234567"),
        ("+86-755-1234-567", "+867551234567"),
        ("(86)7551234567", "+867551234567"),
    ],
)
def test_normalize_number(raw: str, expected: str) -> None:
    """Whitespace and separators are dropped; a missing '+' is added."""
    assert normalize_number(raw) == expected


def test_normalize_number_is_idempotent() -> None:
    """Normalizing an already normalized number changes nothing."""
    once = normalize_number("867551234567")
    assert normalize_number(once) == once


def test_longest_prefix_wins() -> None:
    """Both '+86755' and '+8675512' match; the longer prefix is selected."""
    matched = _rule_set().match("+8675512345678")
    assert matched is not None
    assert matched.rule_id == "rule-75512"


def test_number_without_plus_matches_the_same_rule() -> None:
    """A bare number is equivalent to its '+' prefixed form."""
    rules = _rule_set()
    assert rules.match("867551234567") == rules.match("+867551234567")


def test_block_outranks_translate() -> None:
    """A number matching both a block and a translate rule selects block. REQ-F-7."""
    rules = RuleSet(
        rules=(
            Rule(rule_id="rule-16", prefix="+8616", action=Action.TRANSLATE, target="return-uas"),
            Rule(rule_id="rule-168", prefix="+86168", action=Action.BLOCK),
        )
    )
    matched = rules.match("+861681000000")
    assert matched is not None
    assert matched.rule_id == "rule-168"


def test_block_outranks_a_longer_translate_prefix() -> None:
    """The action rank dominates prefix length: a shorter block still wins."""
    rules = RuleSet(
        rules=(
            Rule(rule_id="rule-16", prefix="+8616", action=Action.BLOCK),
            Rule(
                rule_id="rule-1681",
                prefix="+861681",
                action=Action.TRANSLATE,
                target="return-uas",
            ),
        )
    )
    matched = rules.match("+861681000000")
    assert matched is not None
    assert matched.rule_id == "rule-16"


def test_forward_rule_matches() -> None:
    """A forward rule is selected when no block or translate rule competes."""
    matched = _rule_set().match("+8613800000000")
    assert matched is not None
    assert matched.rule_id == "rule-138"
    assert matched.action is Action.FORWARD


def test_no_match_returns_none() -> None:
    """A number outside every prefix yields no rule. REQ-F-6."""
    assert _rule_set().match("+869990000000") is None
