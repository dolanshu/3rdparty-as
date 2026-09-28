"""Unit tests for a feature switch walking the ADR-0006 change pipeline.

ADR-0020 decides that a switch is a versioned piece of configuration and that it
reuses the rule pipeline instead of opening a second channel: change order →
approval → version repository → staged distribution → rollback. These cases
assert that claim end to end with the modules that already exist — no new
transport, no new store — and they cover **both states** of the switch: the
version under distribution turns it on, the version a rollback falls back to
leaves it off (AGENT.md §3.4).

AGENT.md §5: every timestamp below is injected by the test, no clock is read and
no socket is opened.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Mapping

import pytest

from as_config_service.change_order import ChangeOrder, ChangeState, approve, submit
from as_config_service.distributor import (
    DistributionPlan,
    DistributionState,
    apply_batch,
    begin,
    pending_instances,
)
from as_config_service.version_store import InMemoryVersionStore
from as_platform.api.contract import ConfigBundle, ToggleDTO, toggle_deployment
from as_platform.gating import StaticToggleSource, ToggleScope, is_enabled

pytestmark = pytest.mark.unit

T0 = 1_700_000_000.0
CHANGE_ID = "co-toggle-1"
SUBMITTER = "ops-alice"
APPROVER = "mgr-bob"
SWITCH = "translation.v2"
REMOVAL = "delete the switch when translation.v2 is the only path, at the latest in M6"
SCOPE = ToggleScope(case="translation", number="+86755", call_id="call-1")
FIRST_BATCH = ("as-1", "as-2")
SECOND_BATCH = ("as-3",)
BATCHES = (FIRST_BATCH, SECOND_BATCH)


def _bundle(version: str, enabled: bool) -> ConfigBundle:
    """A configuration version carrying one switch and no rule: a switch travels alone."""
    return ConfigBundle(
        version=version,
        rules=(),
        toggles=(ToggleDTO(name=SWITCH, enabled=enabled, removal_condition=REMOVAL),),
    )


def _approved_order(enabled: bool = True) -> ChangeOrder:
    """A change order for the switch change, walked DRAFT → SUBMITTED → APPROVED."""
    draft = ChangeOrder(
        change_id=CHANGE_ID,
        state=ChangeState.DRAFT,
        bundle=_bundle("v2", enabled),
        created_by=SUBMITTER,
        created_at=T0,
    )
    return approve(submit(draft, SUBMITTER, T0 + 1.0), APPROVER, T0 + 2.0)


def _store(approved: ChangeOrder) -> InMemoryVersionStore:
    """A repository holding version 1 with the switch off and the approved version."""
    store = InMemoryVersionStore(now=lambda: T0)
    store.append(_bundle("v1", enabled=False), T0, change_id="co-toggle-0")
    store.append(approved.bundle, T0 + 3.0, change_id=approved.change_id)
    return store


def _head_version(store: InMemoryVersionStore) -> int:
    """The number of the newest version in ``store``."""
    latest = store.latest()
    assert latest is not None, "the repository under test is never empty"
    return latest.version


def _deployment(store: InMemoryVersionStore, version: int) -> Mapping[str, bool]:
    """The switch table of ``version``, read back out of the repository."""
    stored = store.get(version)
    assert stored is not None, f"version {version} was never written"
    return toggle_deployment(stored.bundle)


def _plan(change_id: str, version: int) -> DistributionPlan:
    """A two-batch grey release of ``version``. See ADR-0006."""
    return DistributionPlan(change_id=change_id, version=version, batches=BATCHES)


def _source(store: InMemoryVersionStore, version: int) -> StaticToggleSource:
    """The gate input built from the switch table of ``version``."""
    return StaticToggleSource(deployment=_deployment(store, version))


def test_a_switch_change_walks_draft_submitted_approved() -> None:
    """A switch is changed by a change order, not by a side channel. ADR-0020, REQ-F-14."""
    draft = ChangeOrder(
        change_id=CHANGE_ID,
        state=ChangeState.DRAFT,
        bundle=_bundle("v2", enabled=True),
        created_by=SUBMITTER,
        created_at=T0,
    )
    submitted = submit(draft, SUBMITTER, T0 + 1.0)

    assert submitted.state is ChangeState.SUBMITTED
    assert submitted.bundle.toggles[0].name == SWITCH

    approved = approve(submitted, APPROVER, T0 + 2.0)

    assert approved.state is ChangeState.APPROVED
    assert approved.approver == APPROVER, "the approver is written into the order itself"
    assert approved.approved_at == T0 + 2.0, "so is the approval time; both are injected"
    assert [entry.action for entry in approved.audit] == ["submit", "approve"]


def test_the_approved_switch_version_is_appended_and_numbered() -> None:
    """Approval writes a new immutable version row, numbered one higher. ADR-0006."""
    approved = _approved_order()
    store = _store(approved)

    first = store.get(1)
    assert first is not None
    assert _deployment(store, 1)[SWITCH] is False, "version 1 leaves the switch off"

    head = store.latest()
    assert head is not None
    assert head.version == 2, "a switch version is numbered like any other version"
    assert head.change_id == CHANGE_ID, "the row remembers the change order that produced it"
    assert _deployment(store, head.version)[SWITCH] is True

    assert [row.version for row in store.history()] == [1, 2]
    assert first.bundle.toggles[0].enabled is False, "an old row is never rewritten"


def test_a_healthy_fleet_completes_the_distribution_and_reports_the_version() -> None:
    """Every batch healthy: COMPLETED, and each instance reports the new version."""
    approved = _approved_order()
    store = _store(approved)
    version = _head_version(store)
    dist = begin(_plan(approved.change_id, version))

    after_first = apply_batch(dist, dict.fromkeys(FIRST_BATCH, True), T0 + 4.0)
    completed = apply_batch(after_first, dict.fromkeys(SECOND_BATCH, True), T0 + 5.0)

    assert after_first.state is DistributionState.IN_PROGRESS, "the grey release is batch by batch"
    assert completed.state is DistributionState.COMPLETED
    assert completed.completed_batches == 2
    assert [report.instance_id for report in completed.reports] == ["as-1", "as-2", "as-3"]
    assert all(report.applied_version == version for report in completed.reports)
    assert _deployment(store, version)[SWITCH] is True, "the distributed version turns it on"


def test_one_unhealthy_instance_rolls_the_switch_version_back() -> None:
    """A failed health check rolls the switch back to the previous version. ADR-0006."""
    approved = _approved_order()
    store = _store(approved)
    version = _head_version(store)
    dist = begin(_plan(approved.change_id, version))

    rolled = apply_batch(dist, {"as-1": True, "as-2": False}, T0 + 4.0)

    assert rolled.state is DistributionState.ROLLED_BACK
    assert rolled.rolled_back_to == version - 1
    assert rolled.rollback_reason == "health check failed"
    assert rolled.completed_batches == 0, "a batch that failed its check does not count"
    assert pending_instances(rolled) == SECOND_BATCH, "the blast radius stays in this batch"


def test_after_the_rollback_the_previous_version_decides_the_switch() -> None:
    """Rolling back moves the marker to the previous row, where the switch is off."""
    approved = _approved_order()
    store = _store(approved)
    version = _head_version(store)
    rolled = apply_batch(
        begin(_plan(approved.change_id, version)),
        {"as-1": True, "as-2": False},
        T0 + 4.0,
    )
    target = rolled.rolled_back_to
    assert target is not None, "a rollback has somewhere to go"

    deployment = _deployment(store, target)
    source = StaticToggleSource(deployment=deployment)

    assert deployment[SWITCH] is False, "the switch is back to the state before the change"
    assert is_enabled(SWITCH, SCOPE, source) is False
    assert _deployment(store, version)[SWITCH] is True, "the rolled-back row is left untouched"
    assert is_enabled(SWITCH, SCOPE, _source(store, version)) is True


def test_the_whole_switch_pipeline_reads_no_clock_and_opens_no_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Time is injected and no socket is opened, end to end. AGENT.md §5."""
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

    approved = _approved_order()
    store = _store(approved)
    version = _head_version(store)
    started = begin(_plan(approved.change_id, version))
    after_first = apply_batch(started, dict.fromkeys(FIRST_BATCH, True), T0)
    completed = apply_batch(after_first, dict.fromkeys(SECOND_BATCH, True), T0 + 1.0)
    evaluated = is_enabled(SWITCH, SCOPE, _source(store, version))

    assert completed.state is DistributionState.COMPLETED
    assert evaluated is True
    assert clock_reads == []
    assert sockets == []
