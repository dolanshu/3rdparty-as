"""Unit tests for feature gating: both states, fail-closed, idempotent.

Acceptance: docs/acceptance/test-plan.md §5.3. See ADR-0020 and hld.md §7.2.
"""

from __future__ import annotations

import socket

import pytest

from as_platform.gating import StaticToggleSource, ToggleScope, is_enabled

pytestmark = pytest.mark.unit

SCOPE = ToggleScope(case="translation", number="+86755", call_id="call-1")


def test_unregistered_toggle_is_disabled() -> None:
    """An unknown name is off, never on: fail-closed. Case 1, ADR-0020."""
    source = StaticToggleSource(deployment={}, overrides={})

    assert is_enabled("not.registered", SCOPE, source) is False


def test_deployment_default_is_off() -> None:
    """The default state of a registered toggle is off. Case 2."""
    source = StaticToggleSource(deployment={"translation.v2": False}, overrides={})

    assert is_enabled("translation.v2", SCOPE, source) is False


def test_deployment_level_can_turn_a_toggle_on() -> None:
    """Layer ① set to on evaluates to on. Case 3."""
    source = StaticToggleSource(deployment={"translation.v2": True}, overrides={})

    assert is_enabled("translation.v2", SCOPE, source) is True


@pytest.mark.parametrize("override", [True, False])
def test_runtime_override_wins_over_the_deployment_level(override: bool) -> None:
    """Layer ② overrides layer ① in both directions. Case 4."""
    source = StaticToggleSource(
        deployment={"translation.v2": not override},
        overrides={("translation.v2", SCOPE.scope_key()): override},
    )

    assert is_enabled("translation.v2", SCOPE, source) is override


def test_runtime_override_is_scoped() -> None:
    """An override for another scope does not apply."""
    other = ToggleScope(case="anti-fraud", number="+86168", call_id="call-2")
    source = StaticToggleSource(
        deployment={"translation.v2": False},
        overrides={("translation.v2", other.scope_key()): True},
    )

    assert is_enabled("translation.v2", SCOPE, source) is False
    assert is_enabled("translation.v2", other, source) is True


def test_repeated_evaluation_of_one_scope_is_consistent() -> None:
    """Gating is idempotent: a split-brain window must not flip it. Case 5."""
    source = StaticToggleSource(
        deployment={"translation.v2": False},
        overrides={("translation.v2", SCOPE.scope_key()): True},
    )

    results = [is_enabled("translation.v2", SCOPE, source) for _ in range(5)]

    assert results == [True] * 5


def test_gating_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """The decision entry point is pure: values come from the injected source. Case 6."""
    sockets: list[str] = []

    def fake_socket(*args: object, **kwargs: object) -> None:
        sockets.append("socket")

    monkeypatch.setattr(socket, "socket", fake_socket)
    source = StaticToggleSource(deployment={"translation.v2": True}, overrides={})

    assert is_enabled("translation.v2", SCOPE, source) is True
    assert is_enabled("unknown", SCOPE, source) is False
    assert sockets == []
