"""Rule set the simulation platform loads into the system under test.

Targets name a next hop only so :func:`as_platform.decision.decide.decide` can
tell FORWARD and TRANSLATE from a refusal. The SIP front sends the outbound
INVITE to the south bridge it was given, and applies the translation rewrite
with the translation use case's own function.
"""

from __future__ import annotations

from as_platform.decision import Rule, RuleSet
from as_platform.decision.rules import Action
from as_translation.decision import TranslationRule


def demo_rules() -> tuple[RuleSet, tuple[TranslationRule, ...]]:
    """Return the first-edition routing rules and the T1 rewrite."""
    target = "sip:uas@south"
    rules = RuleSet(
        rules=(
            Rule(
                rule_id="t1-plus86",
                prefix="+86138",
                action=Action.TRANSLATE,
                target=target,
            ),
            Rule(
                rule_id="t5-forward",
                prefix="+15550001",
                action=Action.FORWARD,
                target=target,
            ),
            Rule(
                rule_id="f1-allow",
                prefix="+15550002",
                action=Action.FORWARD,
                target=target,
            ),
            Rule(
                rule_id="f2-block",
                prefix="+15550003",
                action=Action.BLOCK,
                target=None,
            ),
        )
    )
    translations = (TranslationRule("t1-plus86", "+86138", "+86", "0"),)
    return rules, translations
