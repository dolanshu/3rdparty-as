"""Unit tests for runtime RuleSet loading from env / ConfigBundle JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from as_platform.api.contract import RuleDTO
from as_platform.decision.rules import Action
from as_platform.runtime.ruleset_loader import (
    config_bundle_from_mapping,
    load_ruleset_from_env,
    rules_from_dtos,
)


def test_rules_from_dtos_maps_actions() -> None:
    rules = rules_from_dtos(
        (
            RuleDTO(rule_id="r1", prefix="+86168", action="block"),
            RuleDTO(rule_id="r2", prefix="+1555", action="forward", target="sip:peer@127.0.0.1"),
        )
    )
    assert len(rules.rules) == 2
    assert rules.rules[0].action is Action.BLOCK
    assert rules.rules[1].action is Action.FORWARD
    assert rules.rules[1].target == "sip:peer@127.0.0.1"


def test_config_bundle_from_mapping_minimal() -> None:
    bundle = config_bundle_from_mapping(
        {"version": "v-test", "rules": [{"rule_id": "x", "prefix": "+1", "action": "translate"}]}
    )
    assert bundle.version == "v-test"
    assert bundle.rules[0].action == "translate"


def test_load_ruleset_from_env_inline_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AS_CONFIG_BUNDLE_PATH", raising=False)
    monkeypatch.setenv(
        "AS_RULESET_JSON",
        json.dumps([{"rule_id": "env-r", "prefix": "+99", "action": "block"}]),
    )
    rules = load_ruleset_from_env()
    assert rules is not None
    assert rules.rules[0].rule_id == "env-r"


def test_load_ruleset_from_env_bundle_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AS_RULESET_JSON", raising=False)
    path = tmp_path / "bundle.json"
    path.write_text(
        json.dumps(
            {
                "version": "file-v1",
                "rules": [
                    {
                        "rule_id": "file-r",
                        "prefix": "+86138",
                        "action": "forward",
                        "target": "sip:t@127.0.0.1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AS_CONFIG_BUNDLE_PATH", str(path))
    rules = load_ruleset_from_env()
    assert rules is not None
    assert rules.rules[0].target == "sip:t@127.0.0.1"
