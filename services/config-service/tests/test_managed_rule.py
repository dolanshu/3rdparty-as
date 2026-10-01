"""Management-plane rule schema tests. REQ-F-12."""

from __future__ import annotations

import pytest

from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService

pytestmark = pytest.mark.unit


def _rule(**overrides: object) -> ManagedRule:
    """Build a valid rule, allowing one field to be varied by a test."""
    fields: dict[str, object] = {
        "rule_id": "rule-1",
        "name": "International callers",
        "match_field": MatchField.CALLING,
        "match_mode": MatchMode.PREFIX,
        "match_value": "+8613",
        "target_service": TargetService.TRANSLATION,
        "enabled": True,
    }
    fields.update(overrides)
    return ManagedRule(**fields)  # type: ignore[arg-type]


def test_prefix_rule_matches_calling_and_normalizes_text() -> None:
    """Prefix definitions retain typed fields and canonicalized text. REQ-F-12."""
    rule = _rule(rule_id=" rule-1 ", name=" International callers ", match_value=" +8613 ")

    assert rule.match_field is MatchField.CALLING
    assert rule.match_mode is MatchMode.PREFIX
    assert (rule.rule_id, rule.name, rule.match_value) == (
        "rule-1",
        "International callers",
        "+8613",
    )


def test_regex_rule_matches_called_and_preserves_declarative_pattern() -> None:
    """Regex text is preserved without imposing Python re semantics. REQ-F-12."""
    pattern = "["

    rule = _rule(
        match_field=MatchField.CALLED,
        match_mode=MatchMode.REGEX,
        match_value=pattern,
    )

    assert rule.match_field is MatchField.CALLED
    assert rule.match_mode is MatchMode.REGEX
    assert rule.match_value == pattern


@pytest.mark.parametrize("target_service", tuple(TargetService))
def test_each_target_service_is_supported(target_service: TargetService) -> None:
    """The management schema accepts every REQ-F-12 target service."""
    assert _rule(target_service=target_service).target_service is target_service


@pytest.mark.parametrize("target_service", [TargetService.BLOCK, TargetService.DEFAULT])
def test_empty_target_detail_is_allowed(target_service: TargetService) -> None:
    """Services without additional routing detail can use an empty value."""
    assert _rule(target_service=target_service, target_detail="").target_detail == ""


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("rule_id", " \t "),
        ("name", ""),
        ("name", " \t "),
        ("name", "\x01\x7f"),
        ("name", "International\u202ecallers"),
        ("match_value", ""),
        ("match_value", " \t "),
        ("match_value", "\x01\x7f"),
        ("rule_id", "rule\n1"),
        ("name", "name\rforged"),
        ("match_value", "value\x00suffix"),
        ("target_detail", "detail\nforged"),
    ],
)
def test_blank_control_only_and_injected_text_is_rejected(
    field_name: str, invalid_value: str
) -> None:
    """Rule text rejects blanks and unsafe control/format characters. REQ-F-12."""
    with pytest.raises(ValueError):
        _rule(**{field_name: invalid_value})


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("match_field", "calling"),
        ("match_mode", "prefix"),
        ("target_service", "translation"),
    ],
)
def test_enum_fields_require_typed_enum_values(field_name: str, invalid_value: str) -> None:
    """String values are not silently coerced into schema enums. REQ-F-12."""
    with pytest.raises(TypeError):
        _rule(**{field_name: invalid_value})


@pytest.mark.parametrize("enabled", [0, 1, "true", None])
def test_enabled_requires_an_actual_bool(enabled: object) -> None:
    """Truthy non-bools do not satisfy the enabled field. REQ-F-12."""
    with pytest.raises(TypeError, match="enabled must be a bool"):
        _rule(enabled=enabled)


@pytest.mark.parametrize("enabled", [True, False])
def test_enabled_accepts_both_bool_states(enabled: bool) -> None:
    """Both strict boolean states are represented directly. REQ-F-12."""
    assert _rule(enabled=enabled).enabled is enabled


def test_rule_is_immutable() -> None:
    """A rule definition cannot be mutated after validation. REQ-F-12."""
    rule = _rule()

    with pytest.raises(AttributeError):
        rule.enabled = False  # type: ignore[misc]
