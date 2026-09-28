"""The number-translation use case's decision: kernel verdict plus number rewriting.

This module does **not** judge a call. Judging is the kernel's job
(``as_platform.decision.decide.decide``); this module only answers the one
question the kernel deliberately leaves open: when the verdict is
``TRANSLATE``, what number goes on the outbound leg. Everything else passes
through untouched, so a ``DECLINE`` can never be rewritten into a route and a
``NOT_FOUND`` stays a 404 (REQ-F-6, REQ-F-7).

No SIP concepts appear here: the verdict arrives as a
``DecisionRequest`` and leaves as a ``Decision``. Pure by construction — no
socket, no clock, no global state, and ``received_at`` is an argument that is
only forwarded to the kernel, never read here. See ADR-0002.
"""

from __future__ import annotations

from dataclasses import dataclass

from as_platform.decision.decide import (
    REASON_MATCH_TRANSLATE,
    Decision,
    DecisionAction,
    DecisionRequest,
    decide,
)
from as_platform.decision.rules import RuleSet, normalize_number


@dataclass(frozen=True)
class TranslationRule:
    """One number-rewriting rule: which range it applies to and how to rewrite it.

    Attributes:
        rule_id: Stable identifier, for traces and the console.
        prefix: The number range this rule applies to, in normalized form.
        strip_prefix: The prefix to remove from a matching number, e.g. ``+86``.
        add_prefix: The prefix to prepend after stripping, e.g. ``0``.
    """

    rule_id: str
    prefix: str
    strip_prefix: str
    add_prefix: str


def translate_number(number: str, rule: TranslationRule) -> str:
    """Rewrite one number according to one translation rule.

    The number is normalized first (``as_platform.decision.rules.normalize_number``),
    so the rule's prefixes are always compared against the same form.

    Args:
        number: The number to rewrite, as it arrived.
        rule: The translation rule to apply.

    Returns:
        The rewritten number when the normalized number falls in the rule's
        range; otherwise the normalized number unchanged.
    """
    normalized = normalize_number(number)
    if not normalized.startswith(normalize_number(rule.prefix)):
        return normalized

    body = normalized
    if rule.strip_prefix and body.startswith(rule.strip_prefix):
        body = body[len(rule.strip_prefix) :]
    return f"{rule.add_prefix}{body}"


def find_translation_rule(
    number: str, rules: tuple[TranslationRule, ...]
) -> TranslationRule | None:
    """Select the translation rule governing a number.

    Longest-prefix-first, which is the same winner rule the kernel's rule
    matching uses (REQ-F-6): a narrow range beats the wider range containing it.

    Args:
        number: The number to find a rule for; normalized before matching.
        rules: The candidate translation rules.

    Returns:
        The rule with the longest matching prefix, or ``None`` when none matches.
    """
    normalized = normalize_number(number)

    candidates = [
        (len(normalize_number(rule.prefix)), rule)
        for rule in rules
        if normalized.startswith(normalize_number(rule.prefix))
    ]
    if not candidates:
        return None

    return max(candidates, key=lambda candidate: candidate[0])[1]


def decide_call(
    request: DecisionRequest, rules: RuleSet, translations: tuple[TranslationRule, ...]
) -> Decision:
    """Decide one call: the kernel's verdict, with TRANSLATE targets rewritten.

    ``DECLINE``, ``NOT_FOUND`` and ``FORWARD`` are the kernel's answers and are
    returned unchanged — a declined call must never acquire a target here. Only
    ``TRANSLATE`` is refined: the outbound number is the called number rewritten
    by the winning translation rule, or the normalized called number when no
    translation rule covers it.

    Args:
        request: The request to decide; the caller injects ``received_at``.
        rules: The kernel rule set of the current configuration version.
        translations: The translation rules available to rewrite the number.

    Returns:
        A decision whose ``target`` is the outbound number for ``TRANSLATE``.
    """
    verdict = decide(request, rules)

    if verdict.action is not DecisionAction.TRANSLATE:
        return verdict

    called = normalize_number(request.called_number)
    rule = find_translation_rule(called, translations)
    target = translate_number(called, rule) if rule is not None else called

    return Decision(
        action=DecisionAction.TRANSLATE,
        target=target,
        reason_code=REASON_MATCH_TRANSLATE,
        matched_rule_id=verdict.matched_rule_id,
    )
