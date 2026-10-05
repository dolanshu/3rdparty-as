"""Load :class:`~as_platform.decision.RuleSet` from env or ConfigBundle JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from as_platform.api.contract import ConfigBundle, RuleDTO
from as_platform.decision import Rule, RuleSet
from as_platform.decision.rules import Action

_ACTION_BY_NAME: dict[str, Action] = {
    "forward": Action.FORWARD,
    "translate": Action.TRANSLATE,
    "block": Action.BLOCK,
}


def _action_from_wire(name: str) -> Action:
    key = name.strip().lower()
    if key not in _ACTION_BY_NAME:
        msg = f"unsupported rule action: {name!r}"
        raise ValueError(msg)
    return _ACTION_BY_NAME[key]


def rules_from_dtos(rules: tuple[RuleDTO, ...]) -> RuleSet:
    """Convert internal API rule DTOs into a kernel :class:`RuleSet`."""
    return RuleSet(
        rules=tuple(
            Rule(
                rule_id=dto.rule_id,
                prefix=dto.prefix,
                action=_action_from_wire(dto.action),
                target=dto.target,
            )
            for dto in rules
        )
    )


def _rule_dto_from_mapping(item: dict[str, Any]) -> RuleDTO:
    return RuleDTO(
        rule_id=str(item["rule_id"]),
        prefix=str(item["prefix"]),
        action=str(item["action"]),
        target=item.get("target"),
    )


def config_bundle_from_mapping(data: dict[str, Any]) -> ConfigBundle:
    """Parse a JSON object shaped like :class:`ConfigBundle` (subset allowed)."""
    rules_raw = data.get("rules", ())
    if not isinstance(rules_raw, list):
        msg = "config bundle rules must be a list"
        raise TypeError(msg)
    rules = tuple(_rule_dto_from_mapping(item) for item in rules_raw)
    toggles_raw = data.get("toggles", ())
    toggles: tuple[Any, ...] = ()
    if toggles_raw:
        if not isinstance(toggles_raw, list):
            msg = "config bundle toggles must be a list when present"
            raise TypeError(msg)
        from as_platform.api.contract import ToggleDTO

        toggles = tuple(
            ToggleDTO(
                name=str(t["name"]),
                enabled=bool(t["enabled"]),
                removal_condition=str(t["removal_condition"]),
                scope=str(t.get("scope", "")),
            )
            for t in toggles_raw
        )
    return ConfigBundle(version=str(data.get("version", "unknown")), rules=rules, toggles=toggles)


def load_ruleset_from_env() -> RuleSet | None:
    """Load rules from ``AS_RULESET_JSON`` or ``AS_CONFIG_BUNDLE_PATH`` when set."""
    inline = os.environ.get("AS_RULESET_JSON", "").strip()
    if inline:
        payload = json.loads(inline)
        if isinstance(payload, list):
            rules = tuple(_rule_dto_from_mapping(item) for item in payload)
            return rules_from_dtos(rules)
        if isinstance(payload, dict) and "rules" in payload:
            return rules_from_dtos(config_bundle_from_mapping(payload).rules)
        msg = "AS_RULESET_JSON must be a rule list or object with rules"
        raise ValueError(msg)

    bundle_path = os.environ.get("AS_CONFIG_BUNDLE_PATH", "").strip()
    if bundle_path:
        text = Path(bundle_path).read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            msg = "AS_CONFIG_BUNDLE_PATH must contain a JSON object"
            raise TypeError(msg)
        return rules_from_dtos(config_bundle_from_mapping(data).rules)

    return None
