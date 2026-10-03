"""Unit tests for ManagedRule → ConfigBundle compilation. ADR-0025."""

from __future__ import annotations

import pytest

from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService
from as_config_service.managed_rule_store import StoredManagedRule
from as_config_service.runtime_bundle import (
    BundleCompileError,
    RuleCompileError,
    compile_active_bundle,
    compile_bundle,
    compile_managed_rule,
)
from as_platform.api.contract import RuleDTO

pytestmark = pytest.mark.unit


def _rule(**overrides: object) -> ManagedRule:
    fields: dict[str, object] = {
        "rule_id": "rule-1",
        "name": "Test rule",
        "match_field": MatchField.CALLED,
        "match_mode": MatchMode.PREFIX,
        "match_value": "+86755",
        "target_service": TargetService.TRANSLATION,
        "enabled": True,
        "target_detail": "return-uas",
    }
    fields.update(overrides)
    return ManagedRule(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("target_service", "target_detail", "expected_action", "expected_target"),
    [
        (TargetService.TRANSLATION, "return-uas", "translate", "return-uas"),
        (TargetService.BLOCK, None, "block", None),
        (TargetService.ROUTING, "return-uas", "forward", "return-uas"),
        (TargetService.DEFAULT, None, "forward", None),
        (TargetService.ANTI_FRAUD, None, "forward", None),
    ],
)
def test_called_prefix_target_services_compile_to_expected_rule_dto(
    target_service: TargetService,
    target_detail: str | None,
    expected_action: str,
    expected_target: str | None,
) -> None:
    """Happy path: called + prefix + each target service maps to RuleDTO."""
    rule = _rule(target_service=target_service, target_detail=target_detail)

    assert compile_managed_rule(rule) == RuleDTO(
        rule_id="rule-1",
        prefix="+86755",
        action=expected_action,
        target=expected_target,
    )


def test_disabled_rule_is_omitted_from_bundle() -> None:
    """Disabled rules do not appear in the compiled bundle."""
    bundle = compile_bundle(
        "v-test",
        [
            _rule(rule_id="enabled", enabled=True),
            _rule(rule_id="disabled", enabled=False),
        ],
    )

    assert bundle.version == "v-test"
    assert bundle.rules == (RuleDTO("enabled", "+86755", "translate", "return-uas"),)


def test_calling_field_rule_rejects_compile() -> None:
    """Calling-party match is not representable in RuleDTO v0.1.0."""
    rule = _rule(match_field=MatchField.CALLING)

    with pytest.raises(RuleCompileError, match="CALLING"):
        compile_managed_rule(rule)


def test_regex_rule_rejects_compile() -> None:
    """Regex match mode is not representable in RuleDTO v0.1.0."""
    rule = _rule(match_mode=MatchMode.REGEX, match_value="+8613.*")

    with pytest.raises(RuleCompileError, match="REGEX"):
        compile_managed_rule(rule)


def test_match_value_is_normalized_on_prefix() -> None:
    """Prefix uses kernel number normalization on match_value."""
    rule = _rule(match_value=" 86-755-1234 ")

    assert compile_managed_rule(rule).prefix == "+867551234"


def test_bundle_orders_rules_by_rule_id() -> None:
    """Compiled rules are stably sorted by rule_id (ADR-0025)."""
    bundle = compile_bundle(
        "v1",
        [
            _rule(rule_id="rule-z"),
            _rule(rule_id="rule-a", match_value="+86138"),
            _rule(rule_id="rule-m", match_value="+86168", target_service=TargetService.BLOCK),
        ],
    )

    assert [dto.rule_id for dto in bundle.rules] == ["rule-a", "rule-m", "rule-z"]


def test_multiple_rules_produce_full_bundle() -> None:
    """Several enabled rules compile into one bundle."""
    bundle = compile_bundle(
        "2026.10.03.1",
        [
            _rule(
                rule_id="translate-755",
                target_service=TargetService.TRANSLATION,
                target_detail="return-uas",
            ),
            _rule(
                rule_id="block-168",
                match_value="+86168",
                target_service=TargetService.BLOCK,
                target_detail=None,
            ),
        ],
    )

    assert bundle.version == "2026.10.03.1"
    assert bundle.rules == (
        RuleDTO("block-168", "+86168", "block"),
        RuleDTO("translate-755", "+86755", "translate", "return-uas"),
    )


def test_empty_enabled_set_yields_empty_rules_when_version_supplied() -> None:
    """An all-disabled or empty input yields rules=() with an explicit version."""
    assert compile_bundle("v-empty", []).rules == ()
    assert compile_bundle("v-empty", [_rule(enabled=False)]).rules == ()


def test_bundle_compile_collects_all_rule_errors() -> None:
    """One failing enabled rule fails the whole bundle with per-rule errors."""
    with pytest.raises(BundleCompileError) as exc_info:
        compile_bundle(
            "v1",
            [
                _rule(rule_id="ok"),
                _rule(rule_id="calling", match_field=MatchField.CALLING),
                _rule(rule_id="regex", match_mode=MatchMode.REGEX),
            ],
        )

    rule_ids = {error.rule_id for error in exc_info.value.errors}
    assert rule_ids == {"calling", "regex"}


def test_translation_without_target_detail_rejects() -> None:
    """Translation requires routing detail on the wire."""
    with pytest.raises(RuleCompileError, match="target_detail"):
        compile_managed_rule(_rule(target_detail=None))


def test_compile_active_bundle_skips_tombstones_and_disabled_rules() -> None:
    """Active bundle uses latest non-tombstone enabled rules only."""
    records = (
        StoredManagedRule("enabled", 1, _rule(rule_id="enabled"), "c1", "actor", 1.0),
        StoredManagedRule(
            "disabled", 1, _rule(rule_id="disabled", enabled=False), "c2", "actor", 1.0
        ),
        StoredManagedRule("gone", 1, None, "c3", "actor", 1.0),
    )

    class _Store:
        def list_latest(self) -> tuple[StoredManagedRule, ...]:
            return records

    bundle = compile_active_bundle("42", _Store())

    assert bundle.version == "42"
    assert bundle.rules == (RuleDTO("enabled", "+86755", "translate", "return-uas"),)


def test_compile_active_bundle_propagates_compile_errors() -> None:
    """One bad enabled rule fails the active bundle compile."""
    records = (
        StoredManagedRule(
            "calling",
            1,
            _rule(rule_id="calling", match_field=MatchField.CALLING),
            "c1",
            "actor",
            1.0,
        ),
    )

    class _Store:
        def list_latest(self) -> tuple[StoredManagedRule, ...]:
            return records

    with pytest.raises(BundleCompileError):
        compile_active_bundle("1", _Store())
