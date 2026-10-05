# M6 Load Harness Work-in-Progress Review

> Supersession note (2026-10-03, later update): This file is a historical snapshot of an earlier WIP review state. Subsequent code changes in the same branch addressed several items that were open at that point, including Contact/route-based 2xx dialog targeting, non-2xx INVITE ACK handling, INVITE CPS separation from scheduled attempts, and harness source provenance reporting. Remaining limits still include D8/REQ traceability closure, target-side resource observations for formal measurement evidence, absence of real target-stack measurement results, and unsupported retransmission/forking dialog behaviors. Keep this record unchanged as historical review evidence.

## Object

Independent review of the current M6 work in progress on branch `callload`, against baseline HEAD `0ddedd3525d10825c4dd23c9eb6152d7518a08ab`:

- [`testbed/load/pyproject.toml`](../../testbed/load/pyproject.toml)
- [`testbed/load/src/as_load/harness.py`](../../testbed/load/src/as_load/harness.py)
- [`testbed/load/src/as_load/__main__.py`](../../testbed/load/src/as_load/__main__.py)
- [`testbed/load/tests/test_harness.py`](../../testbed/load/tests/test_harness.py)
- [`testbed/load/README.md`](../../testbed/load/README.md), [`docs/plan.md`](../plan.md), [`docs/acceptance/README.md`](../acceptance/README.md), and the M6 capacity-planning references

The harness source is new/untracked relative to the baseline. The main agent's only source change in this review slice was replacing Python-3.11-only `datetime.UTC` with Python-3.10-compatible `timezone.utc`. This record reviews the WIP; it does not fix the remaining findings or approve M6 acceptance.

## Date and Reviewers

- Date: 2026-10-03
- Standards axis: Independent AI Standards reviewer
- Spec axis: Independent AI Spec reviewer

## Conclusion

**Not approved for capacity measurements.** The Python environment is healthy and the focused test suite passes after the compatibility fix and project resync. However, the load generator still has unresolved SIP protocol and CPS-accounting findings, and no target SIP stack was installed or measured. Loopback test success is not capacity evidence.

## Findings and Fixes/Status

No fixes were made as part of this review record. All findings below remain open.

1. **High — INVITE dialog handling can invalidate target measurements (Spec).** The UAC counts any correlated INVITE 2xx as established, then sends ACK and BYE to the original Request-URI. It does not use Contact as the remote target or apply Record-Route routing. It also sends no ACK for non-2xx INVITE final responses. Consequently, successful dialog setup/teardown is not established for general SIP targets, and generated traffic may not measure the intended target behavior.
2. **High — CPS accounting does not represent INVITE wire rate (Spec).** C6 attempt rates include scheduled attempts even when worker saturation drops them before transmission. The `sent_datagrams` rate aggregates INVITE, ACK, and BYE, so it cannot be reported as wire INVITE CPS. Reported scheduled CPS and aggregate datagram rates must not be treated as measured INVITE CPS.
3. **High — Documentation and implementation scope conflict (Standards and Spec).** The load README says implementation and smoke tests are prohibited until D8 is decided, while the plan says the harness has not started; the reviewed harness, CLI, and tests are present. D8 is still unresolved. The acceptance README has no M6 acceptance entry. These records do not establish authorization, acceptance criteria, or milestone completion for the implementation.
4. **Medium — Source traceability is missing (Standards).** The new harness source does not include the `# See ADR-00NN` traceability required by `AGENT.md` §5. This remains open pending the applicable decision/reference being resolved.
5. **Medium — Evidence does not identify the dirty source tree (Standards).** The evidence records the baseline HEAD but not the identity of the working-tree/untracked harness source that produced the run. A baseline commit alone cannot reproduce or identify this implementation.
6. **Medium — Required saturation observations are absent (Standards).** The summary's `target_resource_observations` is always empty. M6 requires observing the first saturated resource; without observations the harness cannot substantiate that part of the required result.
7. **Medium — Current tests are harness checks, not target-capacity evidence (Spec).** The tests use a scripted loopback UAS and assert UDP message/accounting behavior. They do not exercise a target SIP stack, and the target resource observation list is asserted empty. No capacity result follows from these tests.

Other reviewed points: the Python 3.10 compatibility fix is appropriate; public annotations, real UDP sockets, the integration marker, and the product import boundary appear consistent. No actionable baseline smell findings were reported. No scope-creep finding was identified beyond the unresolved M6 authorization/documentation conflict above.

## Verification

- The system Python is 3.8.10; uv had CPython 3.10.21 installed and selected for the load project, whose requirement is `>=3.10,<3.11`.
- The initial import failure was due to use of `datetime.UTC`, unavailable in Python 3.10. After changing to `timezone.utc`, `uv sync --locked --reinstall` succeeded from the repository root, resolved 43 packages, built workspace packages, and reinstalled 41 packages. `uv.lock` was not changed.
- Before resync, `.venv/bin/pytest` pointed to a neighboring checkout's Python. After resync, it pointed to this repository's `.venv/bin/python3`.
- After resync, `uv run pytest -q testbed/load/tests/test_harness.py` passed: **4 passed in 0.81s**. `uv run python -m pytest` from the repository root also passed all 4 tests. Before resync, the root pytest command failed with `ModuleNotFoundError: as_load.harness`.
- `sipp`, `cmake`, and reSIProcate were absent. `apt-cache` exposed CMake 3.16.3 and `sip-tester`, but no reSIProcate package result. The user is uid 1000 and passwordless sudo is unavailable. No system package installation or native SIP stack installation was attempted; no stuck install/build processes were found.
- No actual target-stack capacity measurement was run.

## Residual Boundaries

- D8 remains undecided; the load README and plan status are inconsistent with the current implementation.
- M4/M5 state is untouched and remains as previously recorded. M7 has not started.
- No capacity metrics, target-stack results, or acceptance are claimed. The loopback tests are only harness-level evidence.
- Maintainer decision and signoff remain pending.