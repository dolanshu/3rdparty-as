"""Staged distribution of a configuration version, with automatic rollback.

ADR-0006 refuses the idea that "written to PostgreSQL" means "live": the fleet is
notified **batch by batch**, every batch is health checked, and a batch that
fails its check **rolls the distribution back to the previous version**
automatically, the rollback being recorded like any other step. REQ-NF-10 asks
for exactly these properties of a change: versionable, traceable, stageable,
rollback-capable. Feature flags travel the same pipeline as rules (ADR-0020,
REQ-G-1), so what this module does to a rule version it also does to a flag
version: there is one staged path, not one per kind of configuration.

A batch is the grey-release unit. Advancing one batch at a time bounds the blast
radius of a bad change to that batch instead of the whole fleet, and it is the
reason a rollback here is cheap: the remedy is to move the effective marker back
one immutable version row, never to rewrite history. See ADR-0006.

Version reporting is how the control plane knows what the fleet actually runs
instead of inferring it from the write time: an instance reports the version it
has loaded, which is the ``AppliedVersionReport`` contract of the internal API
(``as_platform.api.contract``: ``case``, ``version``, ``applied_at``). The
transport side converts that wire shape into the ``InstanceReport`` below, which
carries the numeric version of a version row and the outcome of the instance's
health check. See ADR-0006.

This module is **pure**: no socket, no clock, no global state (AGENT.md §5).
Time is a parameter of every transition, injected by the caller, which is what
makes the audit trail reproducible instead of merely recorded.

The machine:

```text
PENDING      --begin-->                    IN_PROGRESS
IN_PROGRESS  --apply_batch(healthy)-->     IN_PROGRESS | COMPLETED
IN_PROGRESS  --apply_batch(unhealthy)-->   ROLLED_BACK
IN_PROGRESS  --roll_back-->                ROLLED_BACK
```

COMPLETED and ROLLED_BACK are terminal: the distribution is over, and moving it
again would falsify the audit trail that ADR-0006 exists to produce.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum


class DistributionState(Enum):
    """The states a distribution can be in. See ADR-0006."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


# The states after which a distribution is over. See ADR-0006.
_TERMINAL_STATES: frozenset[DistributionState] = frozenset(
    {
        DistributionState.COMPLETED,
        DistributionState.ROLLED_BACK,
    }
)

# Why a rollback happened when no caller gave a reason: an unhealthy batch. See ADR-0006.
_AUTOMATIC_ROLLBACK_REASON = "health check failed"


class IllegalDistributionStateError(Exception):
    """Raised when a distribution is asked to move while it is not in progress.

    A distribution that has not begun has nothing to collect and nothing to roll
    back; one that is completed or rolled back is finished, and moving it again
    would rewrite a closed audit trail. See ADR-0006.

    Attributes:
        state: The state the distribution is in.
    """

    def __init__(self, state: DistributionState) -> None:
        """Build the error naming the state that refuses the move.

        Args:
            state: The state the distribution is in.
        """
        super().__init__(f"illegal distribution state: {state.value}")
        self.state = state


@dataclass(frozen=True)
class InstanceReport:
    """What one instance reported after being notified of a version.

    The kernel-side shape of ``AppliedVersionReport`` (``as_platform.api.contract``),
    narrowed to what staged distribution decides on: which instance, which
    version it loaded, and whether its health check passed. See ADR-0006.

    Attributes:
        instance_id: The instance reporting.
        applied_version: The version the instance has loaded, as numbered in the
            version repository.
        healthy: Whether the instance passed its health check on that version.
    """

    instance_id: str
    applied_version: int
    healthy: bool


@dataclass(frozen=True)
class DistributionPlan:
    """Who is notified of a version, and in which order. See ADR-0006.

    Attributes:
        change_id: The change order this distribution carries out.
        version: The version being distributed.
        batches: The batches, in order; each batch is the instance ids notified
            together. Batching is the grey release: the blast radius of a bad
            change is one batch, not the fleet. An empty tuple means there is
            nothing to distribute.
    """

    change_id: str
    version: int
    batches: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Distribution:
    """One staged distribution, and what it has collected so far. See ADR-0006.

    Attributes:
        plan: What is being distributed, to whom, in which order.
        state: Where the distribution is in the machine above.
        completed_batches: How many batches passed their health check.
        reports: Every instance report collected so far, oldest first.
        rolled_back_to: The version the distribution rolled back to; ``None``
            while it has not rolled back, and ``None`` after a rollback of
            version 1, which has no previous row to go back to.
        rollback_reason: Why it rolled back; ``None`` while it has not.
        updated_at: When it last moved, **injected by the caller**; this module
            reads no clock (AGENT.md §5). ``None`` before the first move.
    """

    plan: DistributionPlan
    state: DistributionState
    completed_batches: int = 0
    reports: tuple[InstanceReport, ...] = ()
    rolled_back_to: int | None = None
    rollback_reason: str | None = None
    updated_at: float | None = None


def rollback_target(version: int) -> int | None:
    """The version a distribution of ``version`` rolls back to, if there is one.

    Rolling back is not "writing the old value back": it moves the effective
    marker to the previous immutable version row, so the target is simply the
    row before. Version rows are numbered from 1, so version 1 — the first
    configuration ever written — has nothing to roll back to. See ADR-0006.

    Args:
        version: The version being distributed.

    Returns:
        ``version - 1`` when that names a version row, else ``None``.
    """
    previous = version - 1
    if previous <= 0:
        return None
    return previous


def begin(plan: DistributionPlan) -> Distribution:
    """Start a planned distribution: PENDING → IN_PROGRESS.

    Beginning notifies nobody: the instances are contacted one batch at a time
    by ``apply_batch``. See ADR-0006.

    Args:
        plan: What to distribute, to whom, in which order.

    Returns:
        A new distribution in IN_PROGRESS, with nothing collected yet.
    """
    pending = Distribution(plan=plan, state=DistributionState.PENDING)
    return replace(pending, state=DistributionState.IN_PROGRESS)


def apply_batch(dist: Distribution, reports: Mapping[str, bool], now: float) -> Distribution:
    """Collect the reports of the current batch and decide what happens next.

    One instance reporting unhealthy rolls the distribution back to the previous
    version and stops it: the remaining batches are never notified, which is what
    keeps a bad change inside its first batch. A batch in which every instance is
    healthy advances the distribution by one, and the last batch completes it.
    See ADR-0006.

    The reports of the current batch are read in batch order; an entry for an
    instance outside that batch is ignored, and a batch instance with no entry
    raises ``KeyError``: advancing a batch on the silence of an instance that was
    notified would hide that it never answered.

    Args:
        dist: The distribution collecting a batch.
        reports: The health of each instance of the current batch, keyed by
            instance id, as reported by the instances themselves.
        now: When the batch was collected, injected by the caller.

    Returns:
        A new distribution: ROLLED_BACK if any instance of the batch is
        unhealthy, otherwise advanced by one batch and COMPLETED once the last
        batch has passed. A plan with no batches has nothing to distribute, so
        the first call completes it.

    Raises:
        IllegalDistributionStateError: If the distribution is not IN_PROGRESS.
        KeyError: If an instance of the current batch did not report.
    """
    _guard(dist)
    batch = _current_batch(dist)
    if batch is None:
        # Nothing left to distribute: a plan without batches is complete the
        # moment it is asked for a batch, rather than stuck in progress. See ADR-0006.
        return replace(dist, state=DistributionState.COMPLETED, updated_at=now)

    collected = tuple(
        InstanceReport(
            instance_id=instance_id,
            applied_version=dist.plan.version,
            healthy=reports[instance_id],
        )
        for instance_id in batch
    )
    if not all(report.healthy for report in collected):
        return replace(
            dist,
            state=DistributionState.ROLLED_BACK,
            reports=(*dist.reports, *collected),
            rolled_back_to=rollback_target(dist.plan.version),
            rollback_reason=_AUTOMATIC_ROLLBACK_REASON,
            updated_at=now,
        )

    completed = dist.completed_batches + 1
    state = (
        DistributionState.COMPLETED
        if completed >= len(dist.plan.batches)
        else DistributionState.IN_PROGRESS
    )
    return replace(
        dist,
        state=state,
        completed_batches=completed,
        reports=(*dist.reports, *collected),
        updated_at=now,
    )


def roll_back(dist: Distribution, reason: str, now: float) -> Distribution:
    """Stop a distribution and move the fleet back one version: → ROLLED_BACK.

    An unhealthy batch rolls back on its own through ``apply_batch``; this is the
    same transition driven by a decision — an operator aborting a rollout, or a
    regression found while it is still in progress. Both are one transition,
    because in both cases the remedy is to move the effective marker back one
    immutable version row. See ADR-0006.

    Args:
        dist: The distribution to roll back.
        reason: Why; kept on the distribution so the audit row written from it
            can be read without a second table.
        now: When, injected by the caller.

    Returns:
        A new distribution in the terminal state ROLLED_BACK, carrying
        ``rolled_back_to`` and ``rollback_reason``.

    Raises:
        IllegalDistributionStateError: If the distribution is not IN_PROGRESS.
    """
    _guard(dist)
    return replace(
        dist,
        state=DistributionState.ROLLED_BACK,
        rolled_back_to=rollback_target(dist.plan.version),
        rollback_reason=reason,
        updated_at=now,
    )


def pending_instances(dist: Distribution) -> tuple[str, ...]:
    """The instances of the plan that have not reported yet.

    The caller uses this to know who still has to be asked: an instance that has
    reported — healthy or not — is no longer pending. Every instance has reported
    once the tuple is empty. See ADR-0006.

    Args:
        dist: The distribution to inspect.

    Returns:
        The instance ids without a report, in plan order.
    """
    reported = {report.instance_id for report in dist.reports}
    return tuple(
        instance_id
        for batch in dist.plan.batches
        for instance_id in batch
        if instance_id not in reported
    )


def is_terminal(state: DistributionState) -> bool:
    """Whether a distribution in ``state`` is finished.

    Args:
        state: The state to test.

    Returns:
        ``True`` for COMPLETED and ROLLED_BACK.
    """
    return state in _TERMINAL_STATES


def _guard(dist: Distribution) -> None:
    """Refuse any move on a distribution that is not in progress.

    Args:
        dist: The distribution being moved.

    Raises:
        IllegalDistributionStateError: If ``dist.state`` is not IN_PROGRESS.
    """
    if dist.state is not DistributionState.IN_PROGRESS:
        raise IllegalDistributionStateError(dist.state)


def _current_batch(dist: Distribution) -> tuple[str, ...] | None:
    """The batch about to be collected.

    Args:
        dist: The distribution being advanced.

    Returns:
        The instance ids of the next batch, or ``None`` when the plan has no
        batch left to distribute.
    """
    batches = dist.plan.batches
    if dist.completed_batches >= len(batches):
        return None
    return batches[dist.completed_batches]
