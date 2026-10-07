"""First-edition call scenarios for the IMS simulation platform.

The identifiers match the M7.1 plan: T1, T4, T5, F1 and F2. T2, T3 and the
later anti-fraud cases are intentionally absent. The harness sends the called
and calling identities; the system under test decides the response code.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CallScenario:
    """One selectable call type.

    Attributes:
        scenario_id: Stable id shown in the UI and in result buckets.
        title: Short label for the test-tool page.
        called_user: User part of the Request-URI.
        calling_user: User part of From and P-Asserted-Identity.
        description: What a passing run is expected to exercise.
    """

    scenario_id: str
    title: str
    called_user: str
    calling_user: str
    description: str


#: Order is the first-edition set from the M7.1 plan. Do not append T2/T3 here.
FIRST_EDITION: tuple[CallScenario, ...] = (
    CallScenario(
        scenario_id="T1",
        title="T1 +86 to 0-prefix",
        called_user="+8613800138000",
        calling_user="+8613911111111",
        description="Translation connects. Called number starts with +86.",
    ),
    CallScenario(
        scenario_id="T4",
        title="T4 short number",
        called_user="10010",
        calling_user="+8613911111111",
        description="No matching prefix. The AS answers 404.",
    ),
    CallScenario(
        scenario_id="T5",
        title="T5 reachable next hop",
        called_user="+155500010001",
        calling_user="+8613911111111",
        description="Forward to the simulated callee. Final response is 200.",
    ),
    CallScenario(
        scenario_id="F1",
        title="F1 allow caller",
        called_user="+155500020002",
        calling_user="+8613000000001",
        description="Allow-listed caller is forwarded.",
    ),
    CallScenario(
        scenario_id="F2",
        title="F2 blocked caller range",
        called_user="+155500030003",
        calling_user="+8613999990002",
        description="Block rule. The product path answers 603; the UI shows that code as received.",
    ),
)

_BY_ID: dict[str, CallScenario] = {item.scenario_id: item for item in FIRST_EDITION}


def scenario_by_id(scenario_id: str) -> CallScenario:
    """Return one first-edition scenario.

    Args:
        scenario_id: ``T1``, ``T4``, ``T5``, ``F1`` or ``F2``.

    Returns:
        The matching scenario.

    Raises:
        ValueError: If ``scenario_id`` is not in the first edition.
    """
    try:
        return _BY_ID[scenario_id]
    except KeyError as error:
        known = ", ".join(item.scenario_id for item in FIRST_EDITION)
        raise ValueError(f"unknown call scenario {scenario_id!r}; known: {known}") from error


def scenario_for_attempt(scenario_ids: tuple[str, ...], attempt_index: int) -> CallScenario | None:
    """Pick the scenario for a zero-based attempt index.

    Args:
        scenario_ids: Enabled ids, in UI order. Empty means the legacy single URI.
        attempt_index: Zero-based index of the scheduled attempt.

    Returns:
        The scenario for this attempt, rotating through ``scenario_ids``, or
        ``None`` when no scenarios are enabled.
    """
    if not scenario_ids:
        return None
    if attempt_index < 0:
        raise ValueError("attempt_index must not be negative")
    return scenario_by_id(scenario_ids[attempt_index % len(scenario_ids)])
