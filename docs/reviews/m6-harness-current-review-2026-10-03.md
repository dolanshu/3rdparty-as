# M6 Load Harness Current Work-in-Progress Review

## Object

Independent review of the authorized current M6 WIP on branch `callload`, comparing the uncommitted working tree with HEAD `0ddedd3525d10825c4dd23c9eb6152d7518a08ab`. Scope includes the load workspace manifest, harness, CLI, and tests; `README.md`; `docs/plan.md`; HLD; ADR-0014 status wording and load README; and prior historical review context.

The earlier [M6 harness WIP review](m6-harness-wip-review-2026-10-03.md) is a historical snapshot and is superseded by this current-state record. Its prior findings on dialog targeting, non-2xx INVITE ACK handling, INVITE CPS accounting, and source provenance were rechecked against the current WIP and are no longer open. ADR-0014 now explicitly frames its older stack-selection quote as acceptance-date context; current stack selection remains documented in ADR-0019. This is the separate current review record for this WIP.

This review records authorized engineering progress only. It does not decide D8, add a REQ, claim M6 completion, or approve capacity acceptance.

## Date and Reviewers

- Date: 2026-10-03
- Standards axis: Independent AI Standards reviewer
- Spec axis: Independent AI Spec reviewer

## Conclusion

**Pass for the current M6 engineering slice only / not approved as M6 capacity completion or acceptance.** The focused harness checks and code-quality checks pass, and the current behavior matches the authorized harness scope. D8 still blocks requirement closure and signoff; no selected-target capacity measurement or target saturation evidence exists. Maintainer signoff is pending.

## Findings and Fixes/Status

1. **Open — D8 test traceability and signoff (Standards).** The tests carry `unit` and `integration` markers but have no valid REQ or contract-case trace because D8 remains unresolved. `AGENT.md` requires each test to trace to a REQ or contract case. This blocks requirement closure/signoff, not the maintainer-authorized engineering WIP. D8 remains open; this review does not resolve it or add a REQ.
2. **No remaining substantive C6 or transaction-correlation mismatch found (Spec).** Top Via branch plus sent-by, Call-ID, and CSeq matching; unresolved-dialog handling; configured-duration rate labels; half-open C6 windows; and full-width availability align with the stated scope. Earlier WIP findings about Contact/route-based 2xx targeting, non-2xx INVITE ACK handling, INVITE CPS separation from scheduled attempts, and source provenance have been addressed.
3. **Evidence boundary — no selected-target or capacity proof (Standards and Spec).** No reSIProcate target stack was installed or measured, and target-side resource observations are unavailable. The harness therefore has no target saturation evidence. The user-local SIPp smoke is one UAS interoperability call only, not reSIProcate or product-target evidence and not a capacity result.
4. **Scope and dependency status.** M4/M5 remain open but are not technical dependencies for this authorized M6 engineering slice. No Go reselection is proposed; ADR-0019's accepted reSIProcate selection remains current. D8 is unresolved, M7 has not started, and no capacity numbers or targets are claimed. M7's existing plan gates remain in force.
5. **Process deviation.** The main agent accidentally spawned two writing subagents concurrently for one overlapping patch, contrary to `AGENT.md` §10.1's one-writer-per-worktree rule. Parallel writes were stopped immediately afterward; the actual tree was inspected and the current code was verified with focused tests, Ruff, and mypy. This deviation is recorded transparently and is not represented as policy-compliant.

## Verification

- `uv run pytest -q testbed/load/tests/test_harness.py`: **44 passed**.
- `uv run pytest -q testbed/load/tests/test_harness.py -m unit`: **24 passed, 20 deselected**.
- `uv run pytest -q testbed/load/tests/test_harness.py -m integration`: **20 passed, 24 deselected**.
- `uv run ruff format --check` on the harness, CLI, and test file: **3 files already formatted**.
- `uv run ruff check` on those three files: **all checks passed**.
- `uv run mypy testbed/load/src/as_load`: **success, 3 source files**.
- `uv run pytest -q tests/test_workspace_layout.py`: **32 passed** after documentation updates.
- `git diff --check`: passed.
- Full `make gate` was attempted and **did not pass**. It stopped at workspace-wide Ruff format check, which reported **8 files would be reformatted** under `testbed/simulators/resip-probe/research`; 243 files were already formatted. These files are outside the M6 slice and were not changed. The run stopped before workspace-wide Ruff check, mypy, and unit tests; no claim is made that all repository gates passed.
- A user-local SIPp 3.6.0 UAS smoke used package files and runtime libraries unpacked only under `/tmp` (no system package installation or `sudo`). SIPp command:

  ```sh
  LD_LIBRARY_PATH=/tmp/as-m6-sipp-20261003/usr/lib/x86_64-linux-gnu /tmp/as-m6-sipp-20261003/usr/bin/sipp -sn uas -i 127.0.0.1 -p 25060 -m 1 -trace_err
  ```

  Harness command from the repository root:

  ```sh
  uv run python -m as_load --host 127.0.0.1 --port 25060 --cps 1 --duration 0.1 --hold 0 --workers 1 --timeout 1 --stack sip-tester --stack-version 3.6.0 --out /tmp/as-m6-sipp-smoke-20261003
  ```

  SIPp reported one successful call, zero failures, zero timeouts, and zero retransmissions. Harness summary: `datagrams_sent=3`, `invite_datagrams_sent=1`, `dialog_acks_sent=1`, `established_sessions=1`, `final_active_sessions=0`, `unresolved_sessions=0`, and an empty error distribution. This is strictly one-call UAS interoperability evidence, not a reSIProcate/product-target smoke or capacity proof.

## Residual Boundaries

- D8's REQ/contract traceability and maintainer signoff remain open. This record does not alter D8 or introduce a requirement.
- No reSIProcate target measurement, target-side resource observations, target saturation evidence, capacity numbers, or capacity targets are available or claimed.
- The SIPp UAS smoke demonstrates only one basic interoperability call; it is not the selected production stack or product target.
- The supported harness profile does not include UDP SIP retransmission timers or multi-2xx/forked-dialog establishment. Results must remain bounded to implemented and tested behavior.
- M4/M5 remain open without being technical dependencies for this M6 engineering slice. M7 has not started and remains subject to its existing gates.
- The previous WIP review remains historical; this current standalone record closes the current-review-record process gap. Maintainer signoff is pending.