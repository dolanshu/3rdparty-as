"""Unit tests for the scale-down guard: which instances may be removed safely.

Every case here must hold without Kubernetes, without a clock and without
state, because the guard only produces a verdict — the operations layer then
drains the selected instances (ADR-0009). No case may encode a capacity
number: O1 is measured in M6, and until then no capacity figure may be
published (AGENT.md §2, plan.md §6). The guard's only input is "does this
instance still carry calls", which is a safety criterion, not a capacity one.

See ADR-0010.
"""

from __future__ import annotations

import itertools
import random
import socket
import time

import pytest

from as_platform.ops.downscale_guard import (
    InstanceLoad,
    ScaleDownPlan,
    may_remove,
    plan_scale_down,
)

pytestmark = pytest.mark.unit


def _load(instance_id: str, active_calls: int, draining: bool = False) -> InstanceLoad:
    return InstanceLoad(instance_id=instance_id, active_calls=active_calls, draining=draining)


def test_every_instance_idle_allows_the_full_reduction() -> None:
    """With nothing in flight, the requested reduction is allowed in full."""
    current = (_load("i-01", 0), _load("i-02", 0), _load("i-03", 0), _load("i-04", 0))

    plan = plan_scale_down(current, desired_replicas=2)

    assert plan.allowed is True
    assert plan.candidates == ("i-01", "i-02")


def test_only_instances_without_calls_are_selected() -> None:
    """A reduction is satisfied out of the idle instances; the busy ones stay."""
    current = (_load("i-01", 3), _load("i-02", 0), _load("i-03", 1), _load("i-04", 0))

    plan = plan_scale_down(current, desired_replicas=2)

    assert plan.allowed is True
    assert plan.candidates == ("i-02", "i-04")


def test_too_few_idle_instances_blocks_but_offers_the_partial_set() -> None:
    """When not enough instances are idle, allowed is False but the usable part
    is still offered, so operations can drain what is safe right now."""
    current = (_load("i-01", 3), _load("i-02", 0), _load("i-03", 1), _load("i-04", 2))

    plan = plan_scale_down(current, desired_replicas=2)

    assert plan.allowed is False
    assert plan.candidates == ("i-02",)
    assert "3 instance(s) are not removable yet" in plan.reason


def test_an_instance_already_draining_is_not_selected_again() -> None:
    """Draining is applied once: selecting an instance twice would re-issue a
    removal that is already under way (ADR-0009)."""
    current = (_load("i-01", 0, draining=True), _load("i-02", 0), _load("i-03", 0))

    plan = plan_scale_down(current, desired_replicas=1)

    assert plan.allowed is True
    assert plan.candidates == ("i-02", "i-03")


def test_candidates_are_ordered_by_load_then_by_instance_id() -> None:
    """The selection is ordered: lightest first, ties broken by instance id."""
    current = (
        _load("i-09", 2),
        _load("i-01", 1),
        _load("i-05", 1),
        _load("i-03", 0),
        _load("i-07", 0),
    )

    plan = plan_scale_down(current, desired_replicas=2, protect_above=5)

    assert plan.allowed is True
    assert plan.candidates == ("i-03", "i-07", "i-01")


def test_the_selection_is_reproducible_for_every_input_order() -> None:
    """The verdict does not depend on the order the instances were reported in;
    two operators looking at the same fleet must see the same plan."""
    loads = (_load("i-04", 0), _load("i-02", 1), _load("i-01", 0), _load("i-03", 1))

    plans = {plan_scale_down(order, desired_replicas=2) for order in itertools.permutations(loads)}

    assert len(plans) == 1
    assert plans.pop().candidates == ("i-01", "i-04")


def test_no_reduction_requested_yields_an_empty_plan() -> None:
    """Growing or holding the replica count is not this guard's business."""
    current = (_load("i-01", 5), _load("i-02", 4))

    for desired in (len(current), len(current) + 1):
        plan = plan_scale_down(current, desired_replicas=desired)

        assert plan.allowed is True, f"desired={desired}"
        assert plan.candidates == (), f"desired={desired}"
        assert plan.reason == "no reduction requested"


def test_a_negative_protection_threshold_does_not_widen_the_protection() -> None:
    """An invalid threshold is clamped to zero: it must never make the guard
    more willing to drop an instance that still carries calls."""
    current = (_load("i-01", 1), _load("i-02", 0))

    plan = plan_scale_down(current, desired_replicas=1, protect_above=-1)

    assert plan.allowed is True
    assert plan.candidates == ("i-02",)
    assert may_remove(_load("i-01", 1), protect_above=-1) is False


def test_may_remove_covers_calls_in_flight_and_draining() -> None:
    """One instance: removable only when it carries nothing and is not draining."""
    assert may_remove(_load("i-01", 0)) is True
    assert may_remove(_load("i-01", 1)) is False
    assert may_remove(_load("i-01", 0, draining=True)) is False
    assert may_remove(_load("i-01", 1, draining=True)) is False


def test_the_plan_is_pure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard reads no clock, opens no socket and rolls no dice: the same
    input yields the same plan, twice and forever."""
    calls: list[str] = []

    def record(name: str) -> object:
        def spy(*args: object, **kwargs: object) -> object:
            calls.append(name)
            raise AssertionError(f"{name} must not be called")

        return spy

    monkeypatch.setattr(socket, "socket", record("socket.socket"))
    monkeypatch.setattr(time, "time", record("time.time"))
    monkeypatch.setattr(time, "monotonic", record("time.monotonic"))
    monkeypatch.setattr(random, "random", record("random.random"))

    current = (_load("i-01", 2), _load("i-02", 0), _load("i-03", 0))

    first: ScaleDownPlan = plan_scale_down(current, desired_replicas=1)
    second: ScaleDownPlan = plan_scale_down(current, desired_replicas=1)

    assert first == second
    assert first.candidates == ("i-02", "i-03")
    assert may_remove(_load("i-01", 2)) is False
    assert calls == []
