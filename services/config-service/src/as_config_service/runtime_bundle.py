"""Compile management-plane ManagedRule rows into internal API ConfigBundle.

Pure functions only — no clock, socket, or store. See ADR-0025.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from as_config_service.managed_rule import ManagedRule, MatchField, MatchMode, TargetService
from as_platform.api.contract import ConfigBundle, RuleDTO
from as_platform.decision.rules import normalize_number


@dataclass(frozen=True)
class RuleCompileError(Exception):
    """One managed rule cannot be represented in RuleDTO v0.1.0."""

    rule_id: str
    reason: str

    def __str__(self) -> str:
        """Human-readable compile failure for logs and tests."""
        return f"rule {self.rule_id!r}: {self.reason}"


@dataclass(frozen=True)
class BundleCompileError(Exception):
    """Bundle assembly failed because one or more enabled rules did not compile."""

    errors: tuple[RuleCompileError, ...]

    def __str__(self) -> str:
        """Summarize every rule-level failure in one message."""
        joined = "; ".join(str(error) for error in self.errors)
        return f"bundle compile failed: {joined}"


class EmptyActiveBundleError(Exception):
    """Activation refused: no enabled compilable rules would reach the fleet."""

    def __str__(self) -> str:
        """Human-readable refusal reason for logs and tests."""
        return "active managed-rule set compiles to an empty fleet bundle"


class _ManagedRuleListingStore(Protocol):
    def list_latest(self) -> tuple[object, ...]: ...


def compile_managed_rule(rule: ManagedRule) -> RuleDTO:
    """Map one managed rule to RuleDTO when it is in the v1 compilable subset."""
    if rule.match_field is not MatchField.CALLED:
        # See ADR-0025 — kernel RuleSet matches called numbers only today.
        raise RuleCompileError(
            rule.rule_id,
            "match_field CALLING is not representable in RuleDTO v0.1.0",
        )
    if rule.match_mode is not MatchMode.PREFIX:
        raise RuleCompileError(
            rule.rule_id,
            "match_mode REGEX is not representable in RuleDTO v0.1.0",
        )

    action, target = _action_and_target(rule)
    prefix = normalize_number(rule.match_value)
    return RuleDTO(
        rule_id=rule.rule_id,
        prefix=prefix,
        action=action,
        target=target,
    )


def compile_active_bundle(
    version: str, managed_rule_store: _ManagedRuleListingStore
) -> ConfigBundle:
    """Compile the current enabled, non-tombstone managed rules into one bundle.

    ``version`` is the distribution plan label (stringified monotonic integer) or
    another non-blank fleet label chosen by the activation caller; it is stored on
    ``ConfigBundle.version`` for traceability alongside ``change_id`` on the
    version row (ADR-0025).
    """
    active: list[ManagedRule] = []
    for stored in managed_rule_store.list_latest():
        rule = getattr(stored, "rule", None)
        if rule is None or not rule.enabled:
            continue
        active.append(rule)
    return compile_bundle(version, active)


def compile_bundle(version: str, rules: Iterable[ManagedRule]) -> ConfigBundle:
    """Compile enabled managed rules into a versioned configuration bundle."""
    if not isinstance(version, str) or not version.strip():
        raise ValueError("version must be a non-blank string")

    compiled: list[RuleDTO] = []
    errors: list[RuleCompileError] = []

    for rule in rules:
        if not rule.enabled:
            continue
        try:
            compiled.append(compile_managed_rule(rule))
        except RuleCompileError as error:
            errors.append(error)

    if errors:
        raise BundleCompileError(tuple(errors))

    compiled.sort(key=lambda dto: dto.rule_id)
    return ConfigBundle(version=version.strip(), rules=tuple(compiled))


def _action_and_target(rule: ManagedRule) -> tuple[str, str | None]:
    """Map TargetService to kernel action strings. See ADR-0025."""
    match rule.target_service:
        case TargetService.TRANSLATION:
            if rule.target_detail is None or not rule.target_detail:
                raise RuleCompileError(
                    rule.rule_id,
                    "translation rules require a non-empty target_detail",
                )
            return "translate", rule.target_detail
        case TargetService.ROUTING | TargetService.DEFAULT | TargetService.ANTI_FRAUD:
            return "forward", rule.target_detail
        case TargetService.BLOCK:
            return "block", None
        case _:
            raise RuleCompileError(
                rule.rule_id,
                f"unsupported target_service {rule.target_service!r}",
            )
