"""Build the outbound Request-URI for a translated or forwarded call.

The platform loads this module by name (``AS_SIP_ROUTE_HOOK``) so the kernel
does not import the use case. The next hop is the S-SBC southbound address the
operator configured; this module only chooses the user part.
"""

from __future__ import annotations

import json
import os
from typing import Any

from as_platform.decision import Decision, DecisionAction
from as_platform.decision.rules import normalize_number
from as_translation.decision import TranslationRule, find_translation_rule, translate_number


def _rules_from_env() -> tuple[TranslationRule, ...]:
    raw = os.environ.get("AS_TRANSLATION_RULES_JSON", "").strip()
    if not raw:
        return ()
    payload: Any = json.loads(raw)
    if not isinstance(payload, list):
        msg = "AS_TRANSLATION_RULES_JSON must be a list"
        raise TypeError(msg)
    rules: list[TranslationRule] = []
    for item in payload:
        if not isinstance(item, dict):
            msg = "each translation rule must be an object"
            raise TypeError(msg)
        rules.append(
            TranslationRule(
                rule_id=str(item["rule_id"]),
                prefix=str(item["prefix"]),
                strip_prefix=str(item.get("strip_prefix", "")),
                add_prefix=str(item.get("add_prefix", "")),
            )
        )
    return tuple(rules)


def _hop_for(transport: str) -> str:
    host = os.environ.get("AS_SIP_NEXT_HOP", "").strip()
    if not host:
        return ""
    if transport.casefold() in {"tls", "sips"}:
        port = os.environ.get("AS_SIP_NEXT_HOP_TLS_PORT", "5061").strip() or "5061"
    else:
        port = os.environ.get("AS_SIP_NEXT_HOP_PORT", "5060").strip() or "5060"
    if host.startswith("sip:") or host.startswith("sips:"):
        return host
    return f"{host}:{port}"


def route_target(decision: Decision, called_number: str, transport: str = "udp") -> str | None:
    """Return the outbound SIP URI for a continue decision, or ``None`` to keep the rule target.

    Args:
        decision: Kernel verdict. Decline and not-found are left unchanged.
        called_number: Called party as it arrived on the inbound INVITE.
        transport: Inbound transport label (``udp``, ``tcp``, ``tls``).

    Returns:
        ``sip:`` or ``sips:`` ``<user>@<next-hop>`` when ``AS_SIP_NEXT_HOP`` is set.
        TLS uses ``sips``. A translate verdict rewrites the user with
        :func:`as_translation.decision.translate_number`.
    """
    if decision.action not in {DecisionAction.FORWARD, DecisionAction.TRANSLATE}:
        return None
    hop = _hop_for(transport)
    if not hop:
        return None
    scheme = "sips" if transport.casefold() in {"tls", "sips"} else "sip"
    user = normalize_number(called_number)
    if decision.action is DecisionAction.TRANSLATE:
        rules = _rules_from_env()
        matched = None
        if decision.matched_rule_id is not None:
            matched = next(
                (rule for rule in rules if rule.rule_id == decision.matched_rule_id),
                None,
            )
        if matched is None:
            matched = find_translation_rule(called_number, rules)
        if matched is not None:
            user = translate_number(called_number, matched)
    return f"{scheme}:{user}@{hop}"
