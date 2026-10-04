# M2 Transport and Native Probe Review

## Object

Current M2 transport-policy seam, native reSIProcate probe TLS self-test setup, certificate generation and documentation, and M2 status documentation on branch `callload`, reviewed against baseline HEAD `6778030efbe8456400b1c065ca415bfb606d16af`. The reviewed working-tree changes are engineering WIP evidence only; no uncommitted file is treated as accepted product implementation. This review changes no requirement or ADR decision.

## Date/Reviewer

- Date: 2026-10-04
- Reviewer: Independent AI Standards/Spec reviewer
- Verification evidence: Main-agent focused checks and native probe runs
- Maintainer signoff: Pending

## Conclusion

**Pass for the current M2 engineering slice only. M2 is not complete, and REQ-S-2/3 are not accepted.** Native testbed smoke is not product transport integration or product acceptance.

## Findings and Fixes

| Finding | Fix / status |
|---|---|
| `TlsConfig` allowed mutual-TLS-required mode without CA trust. | Fixed: `__post_init__` now fails closed for missing or blank CA trust unless explicit server-only mode is selected. The focused seam suite passes 23 tests; Ruff and mypy pass. |
| The probe's TLS self-test used the default `SipStack` constructor, whose default Security was not preloaded. | Fixed for non-external TLS self-test only: the probe uses `SipStackOptions` and injects the passed local test certificate as CA trust. External mode receives no such trust injection. Native S1 TLS succeeds with an empty HOME and no Certificate Validation Failure. |
| Missing TLS certificate or key could be detected after constructing the SIP stack. | Fixed: missing cert/key now fails before stack/listener construction. The negative external-TLS probe exits 1 before listener output. |
| The self-test certificate and generated private key needed bounded use and safer file permissions. | `gen-cert.sh` sets `umask 077`; the certificate is a one-day CA:TRUE certificate with an IP SAN and is explicitly only a self-test trust anchor. Exact generated cert/key paths are ignored. |
| Probe documentation said the selected reSIProcate release lacked certificate reload support. | Corrected: reSIProcate 1.14.0 has `SipStack::reloadCertificates()`, which defers secure transport context reload. The probe neither invokes nor tests it; hot rotation remains open. |
| Probe and status documentation needed to distinguish engineering smoke from product evidence. | Root README reflects M4 engineering closure; the probe README describes S4 ACK as expected, not independently wire-captured. Transport seam documentation no longer claims immutability guarantees live calls. M2 status documentation keeps runtime binding and acceptance open. |

The transport seam remains policy logic, not runtime peer-identity enforcement or a live transport. No production TCP/TLS integration is established by this review.

## Verification

- reSIProcate 1.14.0 source tag commit `632e215c2ca9aee5416bfe1808851ea6fa380044` was cloned under `/tmp/as-resiprocate-m2-20261004`. A minimal CMake build under `/tmp/as-resiprocate-m2-build-20261004` built `libresip`, `libdum`, `librutil`, and `sipdialer`. CMake 3.31.12 came from the signed Kitware Focal apt index; `libpopt-dev` and `libc-ares-dev` were installed with user-authorized sudo. No system-source list was changed; temporary Kitware source/key files were under `/tmp`.
- The native probe CMake build under `/tmp/as-resiprocate-m2-probe-build` succeeded.
- Native S1 UDP completed 100/180/200/ACK/BYE/200 and exited normally.
- Native S1 TLS completed the same sequence with empty HOME and explicit local self-test trust injection; there was no Certificate Validation Failure.
- The negative external-TLS probe with missing cert/key exited 1 before listener output.
- S4 CANCEL reached 487 and LocalCancel/RemoteCancel callbacks. The ACK packet was not independently captured.
- `uv run pytest -q platform/tests/test_transport_seam.py`: 23 passed. Targeted Ruff format/check and `uv run mypy platform/src/as_platform/sip` passed.
- `bash -n testbed/simulators/resip-probe/gen-cert.sh` and `git diff --check` passed.
- Full `make gate` is blocked at Ruff D103 in unrelated `deploy/compose/scripts/m4b-8-seed-users.py` from the master/M4 work. No full-gate pass is claimed.

## Residual Boundaries

- M2 remains incomplete: production platform SIP transport binding/runtime adapter and TLS/peer-policy runtime wiring are not implemented. External S-SBC/operator PKI and mutual-TLS behavior are not verified.
- REQ-S-2/3 remain unaccepted. Although `SipStack::reloadCertificates()` exists, its behavior is untested: preservation of an old active connection, certificate use on a new connection, and dual-certificate overlap all remain open.
- Native reSIProcate probe runs are testbed smoke, not product acceptance or M7 integration. S4 ACK wire capture remains outstanding.
- D8 traceability remains unresolved: ADR-0014's testbed/capacity-testing scope lacks a corresponding PRD requirement mapping. This review does not resolve D8 or change any requirement.
- M6 remains paused pending M2 completion. M7 has not started. M4 is engineering-closed only; this review does not change M5 status or assert M5 completion. Existing real-cluster validation remains outstanding.
- No product TCP/TLS integration, M2 completion, requirement acceptance, or capacity result is claimed. Maintainer signoff remains pending.