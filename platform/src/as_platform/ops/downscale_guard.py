"""Scale-down guard: which instances of a deployment may be removed safely.

The horizontal pod autoscaler decides **whether** to shrink a deployment, from
an aggregate metric such as the average ``active_calls`` per pod. That
aggregate is exactly what makes it unsafe to act on: an average can be low
while individual instances are still carrying calls, and removing one of those
drops the calls on it. This module is the second, per-instance layer: it
decides **which** instances may be removed, and refuses when not enough of
them are quiet (ADR-0010).

Two properties are non-negotiable:

* **No capacity numbers.** There is no default threshold, no target
  utilisation and no replica count here, because O1 (capacity) is measured in
  M6 and no capacity figure may be published before that (AGENT.md §2,
  plan.md §6). The protection threshold is a safety criterion — "is this
  instance still carrying calls" — not a capacity conclusion. It defaults to
  zero: any call in flight protects the instance.
* **Verdict only, no actuation.** This module never calls Kubernetes. It
  returns the instances that may be removed; draining them is the operations
  layer's job, and draining means taking the instance out of rotation first and
  waiting for its calls to reach zero before deleting it (ADR-0009). Selecting
  an instance that is already draining is a no-op re-issue, so it is skipped.

Everything here is pure: no socket, no clock, no global state (AGENT.md §5).
"""

from __future__ import annotations

from dataclasses import dataclass

# No reduction was asked for; scaling up or holding is not this guard's business.
_NO_REDUCTION = "no reduction requested"


@dataclass(frozen=True)
class InstanceLoad:
    """The load reported by one instance of a deployment.

    Attributes:
        instance_id: The identity of the instance, a pod name in practice.
        active_calls: Calls currently in flight on this instance.
        draining: Whether draining has already been started for it. An
            instance being drained is no longer a candidate: re-issuing its
            removal would duplicate an operation already under way. See
            ADR-0009.
    """

    instance_id: str
    active_calls: int
    draining: bool = False


@dataclass(frozen=True)
class ScaleDownPlan:
    """The verdict of one scale-down decision.

    Attributes:
        allowed: Whether the requested reduction can be carried out in full.
        candidates: The instances that may be drained now, cheapest first.
            When ``allowed`` is ``False`` this is the partial set that is
            already safe, so operations can act on it instead of waiting.
        reason: Why the plan looks the way it does; carried into logs and
            alerts so a blocked scale-down is explainable after the fact.
    """

    allowed: bool
    candidates: tuple[str, ...]
    reason: str


def may_remove(load: InstanceLoad, protect_above: int = 0) -> bool:
    """Decide whether one instance may be removed right now.

    Args:
        load: The load reported by the instance.
        protect_above: The protection threshold: an instance carrying more
            than this many calls is protected. Negative values are clamped to
            zero — an invalid threshold must never widen the protection.

    Returns:
        ``True`` only when the instance is not already draining and carries no
        more than the threshold number of calls.
    """
    if load.draining:
        return False  # never re-issue a drain that is under way. See ADR-0009

    return load.active_calls <= max(protect_above, 0)  # See ADR-0010


def plan_scale_down(
    current: tuple[InstanceLoad, ...],
    desired_replicas: int,
    protect_above: int = 0,
) -> ScaleDownPlan:
    """Decide which instances may be removed to reach ``desired_replicas``.

    The selection is the lightest instances first, ordered by
    ``active_calls`` and then by ``instance_id``, so the same fleet always
    yields the same plan regardless of the order instances were reported in.

    Args:
        current: The load of every instance currently running.
        desired_replicas: The replica count the autoscaler wants.
        protect_above: The protection threshold, see :func:`may_remove`.

    Returns:
        The plan: allowed with exactly the requested number of candidates when
        enough instances are quiet, otherwise not allowed with the partial set
        that is safe to drain now. Holding or growing the replica count is
        allowed with no candidates.
    """
    need = len(current) - desired_replicas
    if need <= 0:
        return ScaleDownPlan(allowed=True, candidates=(), reason=_NO_REDUCTION)

    # Sessions live in Redis, not in the process, so a quiet instance can be
    # drained without moving any state (ADR-0002). See ADR-0010.
    selectable = sorted(
        (load for load in current if may_remove(load, protect_above)),
        key=lambda load: (load.active_calls, load.instance_id),
    )

    if len(selectable) < need:
        blocked = len(current) - len(selectable)
        return ScaleDownPlan(
            allowed=False,
            candidates=tuple(load.instance_id for load in selectable),
            reason=(
                f"{blocked} instance(s) are not removable yet; "
                f"{len(selectable)} of {need} can be drained now"
            ),
        )

    return ScaleDownPlan(
        allowed=True,
        candidates=tuple(load.instance_id for load in selectable[:need]),
        reason=f"{need} instance(s) may be drained now",
    )
