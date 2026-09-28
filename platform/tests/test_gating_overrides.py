"""Unit tests for the runtime override layer: granularity, schema, idempotence.

Every case here must hold without Redis, without a clock and without state,
because a split-brain window must not flip a decision (risk R5, open item D3).

See ADR-0020 (two-layer gating) and ADR-0021 (granularity, schema, idempotence).
"""

from __future__ import annotations

import random
import socket
import time

import pytest

from as_platform.gating.overrides import (
    RuntimeOverride,
    fnv1a32,
    in_bucket,
    match_override,
)

pytestmark = pytest.mark.unit

NAME = "translation.v2"
NUMBER = "+8675512345678"
CALL_IDS = tuple(f"call-{index:04d}" for index in range(12))


def _override(
    prefix: str = "+86755",
    percent: int = 100,
    enabled: bool = True,
    name: str = NAME,
) -> RuntimeOverride:
    return RuntimeOverride(
        name=name,
        prefix=prefix,
        percent=percent,
        enabled=enabled,
        removal_condition="removed once the v2 translation path is the default",
    )


def test_percent_at_or_below_zero_never_matches() -> None:
    """A non-positive percentage never puts a call in the bucket. ADR-0021."""
    for percent in (-100, -1, 0):
        for call_id in CALL_IDS:
            assert in_bucket(call_id, percent) is False


def test_percent_at_or_above_one_hundred_always_matches() -> None:
    """A percentage of 100 or more puts every call in the bucket. ADR-0021."""
    for percent in (100, 101, 500):
        for call_id in CALL_IDS:
            assert in_bucket(call_id, percent) is True


def test_percent_boundaries_through_the_override_path() -> None:
    """The same boundaries hold when the override is matched by prefix."""
    never = _override(percent=0)
    always = _override(percent=100)

    for call_id in CALL_IDS:
        assert match_override(NAME, NUMBER, call_id, (never,)) is False
        assert match_override(NAME, NUMBER, call_id, (always,)) is True


def test_repeated_evaluation_of_one_call_is_idempotent() -> None:
    """One call_id evaluates to the same answer every time: no clock, no state.

    A split-brain window re-evaluates a decision; it must not flip it back and
    forth (risk R5, open item D3). See ADR-0021.
    """
    override = _override(percent=50)

    results = [match_override(NAME, NUMBER, "call-0002", (override,)) for _ in range(5)]

    assert results == [True] * 5


def test_a_percentage_splits_calls_inside_one_number_prefix() -> None:
    """Bucketing really splits: within one range some calls hit, some do not."""
    override = _override(percent=50)

    results = [match_override(NAME, NUMBER, call_id, (override,)) for call_id in CALL_IDS]

    assert True in results
    assert False in results


def test_a_disabled_override_returns_false() -> None:
    """An explicit off beats the percentage, even at 100. ADR-0021."""
    disabled = _override(percent=100, enabled=False)

    assert match_override(NAME, NUMBER, "call-0002", (disabled,)) is False


def test_the_longest_matching_prefix_wins() -> None:
    """Among overrides of one name, the longest matching prefix wins. ADR-0021."""
    short = _override(prefix="+86755", percent=100)
    long = _override(prefix="+867551234", percent=0)
    unrelated = _override(prefix="+86756", percent=100)

    assert match_override(NAME, NUMBER, "call-0002", (short, long, unrelated)) is False
    assert match_override(NAME, "+8675599999999", "call-0002", (short, long, unrelated)) is True


def test_no_match_returns_none_and_not_false() -> None:
    """An uncovered range yields None: the deployment level decides. ADR-0021."""
    override = _override(prefix="+86755")

    assert match_override(NAME, "+8616800000000", "call-0002", (override,)) is None
    assert match_override("other.feature", NUMBER, "call-0002", (override,)) is None
    assert match_override(NAME, NUMBER, "call-0002", ()) is None


def test_an_empty_prefix_covers_every_number() -> None:
    """An empty prefix is the deployment-wide range. ADR-0021."""
    override = _override(prefix="", percent=100)

    assert match_override(NAME, "+8616800000000", "call-0002", (override,)) is True


def test_fnv1a32_is_stable_for_known_inputs() -> None:
    """The hash is fixed, so a bucket assignment never drifts between replicas.

    ``""`` and ``"hello world"`` are the published FNV-1a 32-bit vectors. The
    Call-ID value is a regression lock produced by this implementation, not a
    published vector: it freezes the bucket assignment against accidental
    algorithm changes, which would silently move calls between buckets.
    """
    assert fnv1a32("") == 0x811C9DC5
    assert fnv1a32("hello world") == 0xD58B3FA7
    assert fnv1a32("call-0001") == 0xC5556B5F


def test_override_evaluation_reads_no_clock_and_opens_no_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The evaluation is pure: no clock, no randomness, no network. ADR-0021."""
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

    override = _override(percent=50)
    for call_id in CALL_IDS:
        assert match_override(NAME, NUMBER, call_id, (override,)) is not None

    assert fnv1a32("call-0001") == 0xC5556B5F
    assert calls == []
