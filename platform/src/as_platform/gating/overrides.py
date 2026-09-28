"""Runtime override evaluation: the granularity and schema of layer ② gating.

ADR-0020 splits feature gating into a deployment-wide switch (layer ①) and a
fine-grained runtime override (layer ②). This module decides the shape of layer
②, as adjudicated by ADR-0021:

* **Granularity is the number prefix (range), plus an optional stable percentage
  split over the Call-ID.** There is no per-user override (the product is a
  number-domain AS and does not speak Diameter Sh, AGENT.md §2) and no durable
  per-call override (state growth and audit complexity outweigh the benefit).
* **The percentage split is idempotent.** It is derived from
  ``FNV-1a 32-bit(call_id) % 100``, so it uses no clock, no randomness and no
  stored state. Re-evaluating the same call in a Redis split-brain window gives
  the same answer (risk R5, open item D3).
* **Fail-closed.** An uncovered number yields ``None``, never ``True``: the
  deployment level then decides, exactly as in ``gating.is_enabled``.

Everything here is pure: no socket, no clock, no global state (AGENT.md §5).
"""

from __future__ import annotations

from dataclasses import dataclass

from as_platform.decision.rules import normalize_number

# FNV-1a 32-bit constants. The hash is chosen over a random or time-based split
# because it is a pure function of the Call-ID: the same call lands in the same
# bucket on every replica and on every re-evaluation. See ADR-0021
_FNV_OFFSET_BASIS = 0x811C9DC5
_FNV_PRIME = 0x01000193
_MASK_32 = 0xFFFFFFFF

# One bucket per percent, so ``percent`` reads directly as "share of traffic".
_BUCKETS = 100


@dataclass(frozen=True)
class RuntimeOverride:
    """One runtime override item, the layer ② schema of ADR-0021.

    ``prefix`` and ``enabled`` make an override structurally identical to a
    routing rule (`as_platform.decision.rules.Rule`: a prefix plus attributes),
    so both ride the same configuration governance pipeline (ADR-0006).

    Attributes:
        name: The feature name this override belongs to.
        prefix: The number range, in normalized form like ``Rule.prefix``; the
            empty string covers every number, which is the deployment-wide range.
        percent: The share of calls in the range that the override applies to,
            as an integer 0-100. Values outside that range are clamped by
            :func:`in_bucket`.
        enabled: Whether the override is on. An explicit off outranks the
            percentage.
        removal_condition: When this scaffolding is torn out; recorded so the
            override does not become permanent switch debt (ADR-0020).
    """

    name: str
    prefix: str
    percent: int
    enabled: bool
    removal_condition: str


def fnv1a32(text: str) -> int:
    """Hash a string with FNV-1a 32-bit.

    Args:
        text: The text to hash; a Call-ID in this module.

    Returns:
        The 32-bit FNV-1a digest as a non-negative integer.
    """
    digest = _FNV_OFFSET_BASIS
    for byte in text.encode("utf-8"):
        digest = ((digest ^ byte) * _FNV_PRIME) & _MASK_32
    return digest


def in_bucket(call_id: str, percent: int) -> bool:
    """Decide whether one call falls in the first ``percent`` of its range.

    Args:
        call_id: The Call-ID; the only input to the split.
        percent: The share of traffic to take, 0-100. Values below or equal to 0
            take nothing, values at or above 100 take everything.

    Returns:
        ``True`` when the call is inside the percentage of the range.
    """
    if percent <= 0:
        return False  # a non-positive share takes nothing. See ADR-0021
    if percent >= 100:
        return True  # a full share takes everything. See ADR-0021

    return fnv1a32(call_id) % _BUCKETS < percent


def match_override(
    name: str,
    number: str,
    call_id: str,
    overrides: tuple[RuntimeOverride, ...],
) -> bool | None:
    """Evaluate the runtime overrides of one feature for one call.

    Among the overrides of ``name`` whose prefix matches the number, the longest
    prefix wins — the same ordering as ``RuleSet.match``. A disabled override
    switches the feature off regardless of its percentage; otherwise the
    percentage split decides.

    Args:
        name: The feature name to evaluate.
        number: The number being judged, in any form `normalize_number` accepts.
        call_id: The Call-ID, the input of the percentage split.
        overrides: The configured runtime overrides, in any order.

    Returns:
        ``True`` or ``False`` when an override applies, ``None`` when no
        override covers this number, leaving the deployment level to decide.
    """
    normalized = normalize_number(number)

    candidates = [
        override
        for override in overrides
        if override.name == name and normalized.startswith(override.prefix)
    ]
    if not candidates:
        return None  # fail-closed: uncovered means "not decided here". See ADR-0020

    winner = max(candidates, key=lambda override: len(override.prefix))
    if not winner.enabled:
        return False  # an explicit off outranks the percentage. See ADR-0021

    return in_bucket(call_id, winner.percent)
