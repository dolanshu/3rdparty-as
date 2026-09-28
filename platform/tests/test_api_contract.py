"""Unit tests for the internal API contract: a switch is one kind of configuration.

ADR-0020 puts feature switches on the same pipeline as rules: one version of the
configuration carries both, and both are governed by the same change order, the
same version repository and the same staged distribution (ADR-0006). These cases
pin the contract half of that — how a switch travels inside a ``ConfigBundle``,
that its default state is off, and that a name no version declares stays off
(fail-closed, REQ-G-1).

AGENT.md §3.4 asks for both states of a switch to be covered, so on and off are
asserted separately below instead of only through the happy path.
"""

from __future__ import annotations

import dataclasses
import socket
import time

import pytest

from as_platform.api.contract import ConfigBundle, RuleDTO, ToggleDTO, toggle_deployment
from as_platform.gating import StaticToggleSource, ToggleScope, is_enabled

pytestmark = pytest.mark.unit

SCOPE = ToggleScope(case="translation", number="+86755", call_id="call-1")
RULE = RuleDTO(rule_id="rule-755", prefix="+86755", action="translate", target="return-uas")
REMOVAL = "delete the switch when translation.v2 is the only path, at the latest in M6"


def _bundle(*toggles: ToggleDTO) -> ConfigBundle:
    """A configuration version carrying ``toggles``; with a rule unless told otherwise."""
    return ConfigBundle(version="v2", rules=(RULE,), toggles=toggles)


def _switch(enabled: bool) -> ToggleDTO:
    """The switch ``translation.v2`` in the state ``enabled``."""
    return ToggleDTO(name="translation.v2", enabled=enabled, removal_condition=REMOVAL)


def test_a_bundle_without_switches_defaults_to_none() -> None:
    """A version written before any switch existed stays constructible. ADR-0020."""
    bundle = ConfigBundle(version="v1", rules=(RULE,))

    assert bundle.toggles == ()
    assert toggle_deployment(bundle) == {}


def test_a_switch_off_is_the_default_state() -> None:
    """The default state of a switch is off, and the fold keeps that ``False``. §3.4."""
    bundle = _bundle(_switch(enabled=False))

    assert toggle_deployment(bundle) == {"translation.v2": False}


@pytest.mark.parametrize("enabled", [True, False])
def test_the_fold_keeps_both_states(enabled: bool) -> None:
    """Both states reach the deployment table; ``False`` is not filtered out. §3.4."""
    off = ToggleDTO(name="other.v1", enabled=False, removal_condition=REMOVAL)
    bundle = _bundle(_switch(enabled=True), off)

    deployment = toggle_deployment(bundle)

    assert deployment["translation.v2"] is True
    assert deployment["other.v1"] is False, "a switched-off flag is a configured value"


def test_a_switch_cannot_be_declared_without_a_removal_condition() -> None:
    """No way out is switch debt, so the removal condition is not optional. ADR-0020."""
    required = {
        field.name
        for field in dataclasses.fields(ToggleDTO)
        if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING
    }

    assert required == {"name", "enabled", "removal_condition"}
    assert _switch(enabled=True).scope == "", "no scope means the deployment-wide value"


def test_an_undeclared_switch_is_absent_and_evaluates_to_off() -> None:
    """A name this version does not declare is off, never unknown: fail-closed. REQ-G-1."""
    deployment = toggle_deployment(_bundle(_switch(enabled=True)))
    source = StaticToggleSource(deployment=deployment)

    assert "not.declared" not in deployment
    assert is_enabled("not.declared", SCOPE, source) is False


def test_the_folded_deployment_drives_gating_in_both_states() -> None:
    """On evaluates to on and off to off: the contract and the gate agree. ADR-0020."""
    on_source = StaticToggleSource(deployment=toggle_deployment(_bundle(_switch(enabled=True))))
    off_source = StaticToggleSource(deployment=toggle_deployment(_bundle(_switch(enabled=False))))

    assert is_enabled("translation.v2", SCOPE, on_source) is True
    assert is_enabled("translation.v2", SCOPE, off_source) is False


def test_the_fold_is_pure_and_touches_no_clock_or_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same input, same table; no clock read, no socket opened. AGENT.md §5."""
    clock_reads: list[str] = []
    sockets: list[str] = []

    def fake_time() -> float:
        clock_reads.append("time")
        return 0.0

    def fake_monotonic() -> float:
        clock_reads.append("monotonic")
        return 0.0

    def fake_socket(*args: object, **kwargs: object) -> None:
        sockets.append("socket")

    monkeypatch.setattr(time, "time", fake_time)
    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    monkeypatch.setattr(socket, "socket", fake_socket)

    bundle = _bundle(_switch(enabled=True))
    first = toggle_deployment(bundle)
    second = toggle_deployment(bundle)
    source = StaticToggleSource(deployment=first)

    assert first == second
    assert is_enabled("translation.v2", SCOPE, source) is True
    assert clock_reads == []
    assert sockets == []
