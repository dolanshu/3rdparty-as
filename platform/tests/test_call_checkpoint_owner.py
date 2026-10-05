"""Unit tests: checkpoint v2 owner/commit fencing and lifecycle (M7.4–M7.5)."""

from __future__ import annotations

import json

import pytest

from as_platform.state.call_checkpoint import (
    CallCheckpointCommit,
    CallCheckpointLifecycle,
    CallStateCheckpoint,
    CallStateCheckpointRepository,
    DialogLegCheckpoint,
)
from as_platform.state.in_memory import InMemoryStateStore

pytestmark = pytest.mark.contract


def _leg(call_id: str) -> DialogLegCheckpoint:
    return DialogLegCheckpoint(
        call_id=call_id,
        local_tag="l",
        remote_tag="r",
        local_uri="sip:a@127.0.0.1",
        remote_uri="sip:b@127.0.0.1",
        remote_target="sip:b@127.0.0.1",
        route_set=(),
        local_cseq=1,
        remote_cseq=1,
    )


def _checkpoint(
    *,
    owner_generation: int = 0,
    committed: bool = True,
) -> CallStateCheckpoint:
    return CallStateCheckpoint(
        state="established",
        uas_leg=_leg("uas@127.0.0.1"),
        uac_leg=_leg("uac@127.0.0.1"),
        owner_generation=owner_generation,
        committed=committed,
    )


def test_schema_v1_round_trip_without_owner_fields() -> None:
    store = InMemoryStateStore(now=lambda: 1.0)
    repository = CallStateCheckpointRepository(
        store=store, ttl_seconds=60, allowed_header_namespaces={}
    )
    raw_v1 = json.dumps(
        {
            "schema_version": 1,
            "state": "established",
            "uas_leg": {
                "call_id": "uas@127.0.0.1",
                "local_tag": "l",
                "remote_tag": "r",
                "local_uri": "sip:a@127.0.0.1",
                "remote_uri": "sip:b@127.0.0.1",
                "remote_target": "sip:b@127.0.0.1",
                "route_set": [],
                "local_cseq": 1,
                "remote_cseq": 1,
            },
            "uac_leg": {
                "call_id": "uac@127.0.0.1",
                "local_tag": "l",
                "remote_tag": "r",
                "local_uri": "sip:a@127.0.0.1",
                "remote_uri": "sip:b@127.0.0.1",
                "remote_target": "sip:b@127.0.0.1",
                "route_set": [],
                "local_cseq": 1,
                "remote_cseq": 1,
            },
            "extensions": [],
        }
    ).encode("utf-8")
    store.set("as:translation:call:uas@127.0.0.1", raw_v1, ttl_seconds=60)
    loaded = repository.load(case="translation", call_key="uas@127.0.0.1")
    assert loaded is not None
    assert loaded.owner_generation == 0
    assert loaded.committed is True


def test_commit_helper_requires_committed_before_side_effect() -> None:
    pending = _checkpoint(owner_generation=1, committed=False)
    commit = CallCheckpointCommit(pending)
    with pytest.raises(RuntimeError, match="not committed"):
        commit.require_committed_before_side_effect()
    committed = commit.mark_committed()
    CallCheckpointCommit(committed).require_committed_before_side_effect()


def test_save_if_generation_fences_stale_owner() -> None:
    store = InMemoryStateStore(now=lambda: 1000.0)
    repository = CallStateCheckpointRepository(
        store=store, ttl_seconds=120, allowed_header_namespaces={}
    )
    first = _checkpoint(owner_generation=0, committed=True)
    repository.save(case="translation", call_key="key", checkpoint=first)
    bumped = CallCheckpointCommit(first).with_bumped_generation()
    committed_bump = CallCheckpointCommit(bumped).mark_committed()
    assert not repository.save_if_generation(
        "translation", "key", committed_bump, expected_generation=99
    )
    assert repository.save_if_generation(
        "translation", "key", committed_bump, expected_generation=0
    )
    loaded = repository.load(case="translation", call_key="key")
    assert loaded is not None
    assert loaded.owner_generation == 1


def test_lifecycle_renew_and_terminal_delete() -> None:
    clock = [1000.0]

    def now() -> float:
        return clock[0]

    store = InMemoryStateStore(now=now)
    repository = CallStateCheckpointRepository(
        store=store, ttl_seconds=30, allowed_header_namespaces={}
    )
    lifecycle = CallCheckpointLifecycle(repository)
    repository.save(case="translation", call_key="key", checkpoint=_checkpoint())
    assert lifecycle.renew("translation", "key", ttl_seconds=45) is True
    assert lifecycle.renew("translation", "missing") is False
    lifecycle.mark_terminal_and_delete("translation", "key")
    assert repository.load(case="translation", call_key="key") is None
