"""Unit tests for the ADR-0006 staged distributor.

REQ-NF-10 (a configuration change must be stageable and rollback-capable),
ADR-0006 (batch by batch, a health check per batch, automatic rollback when a
check fails) and AGENT.md §5: this module is pure — no clock, no socket, no
global state. Every timestamp below is injected by the test.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Mapping

import pytest

from as_config_service.distributor import (
    Distribution,
    DistributionPlan,
    DistributionState,
    IllegalDistributionStateError,
    InstanceReport,
    apply_batch,
    begin,
    pending_instances,
    roll_back,
    rollback_target,
)

pytestmark = pytest.mark.unit

T0 = 1_700_000_000.0
CHANGE_ID = "co-1"
VERSION = 3
FIRST_BATCH = ("as-1", "as-2")
SECOND_BATCH = ("as-3",)


def _plan(
    batches: tuple[tuple[str, ...], ...] = (FIRST_BATCH, SECOND_BATCH),
    version: int = VERSION,
) -> DistributionPlan:
    """A distribution plan over ``batches``; two batches unless told otherwise."""
    return DistributionPlan(change_id=CHANGE_ID, version=version, batches=batches)


def _healthy(instance_ids: tuple[str, ...]) -> Mapping[str, bool]:
    """The reports of a batch in which every instance passed its health check."""
    return dict.fromkeys(instance_ids, True)


def _in_progress() -> Distribution:
    """A distribution that has begun and applied nothing yet."""
    return begin(_plan())


def _completed() -> Distribution:
    """A distribution whose every batch passed its health check."""
    after_first = apply_batch(_in_progress(), _healthy(FIRST_BATCH), T0)
    return apply_batch(after_first, _healthy(SECOND_BATCH), T0 + 1.0)


def _rolled_back() -> Distribution:
    """A distribution that failed the health check of its first batch."""
    return apply_batch(_in_progress(), {"as-1": True, "as-2": False}, T0)


def test_two_healthy_batches_walk_to_completed() -> None:
    """One batch per call, and the last healthy batch completes the plan. ADR-0006."""
    started = _in_progress()
    assert started.state is DistributionState.IN_PROGRESS

    after_first = apply_batch(started, _healthy(FIRST_BATCH), T0)
    assert after_first.state is DistributionState.IN_PROGRESS
    assert after_first.completed_batches == 1
    assert len(after_first.reports) == 2

    after_second = apply_batch(after_first, _healthy(SECOND_BATCH), T0 + 1.0)
    assert after_second.state is DistributionState.COMPLETED
    assert after_second.completed_batches == 2
    assert len(after_second.reports) == 3
    assert after_second.rolled_back_to is None
    assert [report.instance_id for report in after_second.reports] == [
        "as-1",
        "as-2",
        "as-3",
    ]
    assert all(report.healthy for report in after_second.reports)
    assert all(report.applied_version == VERSION for report in after_second.reports)


def test_unhealthy_instance_rolls_back_without_advancing() -> None:
    """One unhealthy instance rolls the whole distribution back to the previous version."""
    started = _in_progress()

    rolled = apply_batch(started, {"as-1": True, "as-2": False}, T0)

    assert rolled.state is DistributionState.ROLLED_BACK
    assert rolled.rolled_back_to == 2
    assert rolled.rollback_reason == "health check failed", "an automatic rollback says why"
    assert rolled.updated_at == T0
    assert rolled.completed_batches == 0, "a batch that failed its check does not count"
    assert rolled.reports == (
        InstanceReport(instance_id="as-1", applied_version=VERSION, healthy=True),
        InstanceReport(instance_id="as-2", applied_version=VERSION, healthy=False),
    )
    assert pending_instances(rolled) == SECOND_BATCH, "the next batch is never notified"

    with pytest.raises(IllegalDistributionStateError):
        apply_batch(rolled, _healthy(SECOND_BATCH), T0 + 1.0)


def test_explicit_roll_back_records_reason_and_target() -> None:
    """An operator may stop a healthy distribution; the reason travels with the record."""
    after_first = apply_batch(_in_progress(), _healthy(FIRST_BATCH), T0)

    rolled = roll_back(after_first, "operator aborted", T0 + 1.0)

    assert rolled.state is DistributionState.ROLLED_BACK
    assert rolled.rolled_back_to == 2
    assert rolled.rollback_reason == "operator aborted"
    assert rolled.updated_at == T0 + 1.0
    assert rolled.completed_batches == 1, "the batch already applied stays recorded"


@pytest.mark.parametrize(
    ("version", "target"),
    [(1, None), (2, 1), (3, 2), (0, None)],
)
def test_rollback_target(version: int, target: int | None) -> None:
    """Rollback moves the marker back one immutable row; version 1 has nowhere to go."""
    assert rollback_target(version) == target


def test_pending_instances_shrinks_and_empties() -> None:
    """The caller can ask who has not reported yet, until nobody is left."""
    started = _in_progress()
    assert pending_instances(started) == FIRST_BATCH + SECOND_BATCH

    after_first = apply_batch(started, _healthy(FIRST_BATCH), T0)
    assert pending_instances(after_first) == SECOND_BATCH

    completed = apply_batch(after_first, _healthy(SECOND_BATCH), T0 + 1.0)
    assert pending_instances(completed) == ()


def test_begin_leaves_pending_for_in_progress() -> None:
    """PENDING → IN_PROGRESS: a planned distribution has not notified anybody yet."""
    pending = Distribution(plan=_plan(), state=DistributionState.PENDING)
    started = begin(pending.plan)

    assert pending.state is DistributionState.PENDING
    assert started.state is DistributionState.IN_PROGRESS
    assert started.completed_batches == 0
    assert started.reports == ()
    assert started.rolled_back_to is None
    assert started.rollback_reason is None


def test_pending_distribution_refuses_to_move() -> None:
    """A distribution that has not begun cannot collect a batch or roll back."""
    pending = Distribution(plan=_plan(), state=DistributionState.PENDING)

    with pytest.raises(IllegalDistributionStateError) as caught:
        apply_batch(pending, _healthy(FIRST_BATCH), T0)

    assert DistributionState.PENDING.value in str(caught.value)

    with pytest.raises(IllegalDistributionStateError):
        roll_back(pending, "not started", T0)


@pytest.mark.parametrize(
    "factory",
    [_completed, _rolled_back],
    ids=["completed", "rolled_back"],
)
def test_terminal_state_refuses_further_moves(factory: Callable[[], Distribution]) -> None:
    """COMPLETED and ROLLED_BACK are the end of the line, and they say so. ADR-0006."""
    dist = factory()

    with pytest.raises(IllegalDistributionStateError) as caught:
        apply_batch(dist, _healthy(SECOND_BATCH), T0 + 9.0)

    assert dist.state.value in str(caught.value)

    with pytest.raises(IllegalDistributionStateError) as caught_rollback:
        roll_back(dist, "too late", T0 + 9.0)

    assert dist.state.value in str(caught_rollback.value)


def test_every_transition_returns_a_new_object() -> None:
    """No transition rewrites the distribution it was given."""
    started = _in_progress()
    after_first = apply_batch(started, _healthy(FIRST_BATCH), T0)

    assert after_first is not started
    assert started.state is DistributionState.IN_PROGRESS
    assert started.completed_batches == 0
    assert started.reports == ()
    assert started.rolled_back_to is None
    assert started.rollback_reason is None

    rolled = roll_back(after_first, "health check failed", T0 + 1.0)

    assert rolled is not after_first
    assert after_first.state is DistributionState.IN_PROGRESS
    assert after_first.completed_batches == 1
    assert len(after_first.reports) == 2
    assert after_first.rolled_back_to is None
    assert after_first.rollback_reason is None


def test_plan_without_batches_completes_on_first_apply() -> None:
    """Zero batches: there is nothing to distribute, so the first apply completes it."""
    started = begin(_plan(batches=()))
    assert started.state is DistributionState.IN_PROGRESS

    finished = apply_batch(started, {}, T0)

    assert finished.state is DistributionState.COMPLETED
    assert finished.completed_batches == 0
    assert finished.reports == ()
    assert pending_instances(finished) == ()


def test_distribution_reads_no_clock_and_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Time is injected by the caller and no socket is opened. AGENT.md §5."""
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

    started = begin(_plan())
    after_first = apply_batch(started, _healthy(FIRST_BATCH), T0)
    completed = apply_batch(after_first, _healthy(SECOND_BATCH), T0 + 1.0)
    automatic = apply_batch(started, {"as-1": False, "as-2": True}, T0)
    rolled = roll_back(after_first, "operator aborted", T0 + 2.0)
    pending = pending_instances(after_first)
    target = rollback_target(VERSION)

    assert completed.state is DistributionState.COMPLETED
    assert automatic.state is DistributionState.ROLLED_BACK
    assert rolled.state is DistributionState.ROLLED_BACK
    assert pending == SECOND_BATCH
    assert target == 2
    assert clock_reads == []
    assert sockets == []
