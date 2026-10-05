# M2 Native Probe Review

## Object

Current authorized M2 WIP on branch `callload`, reviewed against baseline HEAD `6778030efbe8456400b1c065ca415bfb606d16af`. Scope: the platform transport-policy seam and its tests, plus the testbed reSIProcate native probe, README, and certificate-generation script. This review does not amend ADRs or requirements.

## Date/Reviewers

- Date: 2026-10-04
- Independent AI Standards/Spec reviewer
- Main-agent verification

## Conclusion

**Pass for current M2 engineering slice only; M2 and REQ acceptance remain open.** Maintainer signoff is pending.

## Findings and Fixes

| Finding | Fix / status |
|---|---|
| `TlsConfig` allowed `require_client_certificate=True` without a CA path, despite documenting that this mode verifies peer certificates. | Fixed with fail-closed `__post_init__` validation. Tests cover missing and blank CA paths and explicit server-only TLS. The transport test module has 23 passing tests; Ruff and mypy pass for the touched platform SIP code. |
| The native reSIProcate TLS self-test returned 503 because the old `SipStack()` constructor did not preload default Security. | Fixed in the testbed probe only: non-external TLS self-test mode constructs `SipStackOptions`, adds the supplied local certificate to that instance's CA trust, and constructs the stack with those options. External mode receives no trust injection. S1 TLS now succeeds with an empty HOME using the local certificate; S1 UDP succeeds. This is not production trust configuration. |
| External TLS mode validated missing certificate/key files only after allocating the SIP stack. | Validation now occurs before stack construction. A negative external-mode run exits 1 before emitting listener-port output. |
| Generated private-key permissions and repository hygiene needed explicit handling. | `gen-cert.sh` sets `umask 077` and emits a one-day self-signed CA:TRUE test certificate with an IP SAN. Narrow ignore rules cover only the probe's generated `cert.pem` and `key.pem`; neither generated file is in the repository. |
| The probe documentation incorrectly implied the selected reSIProcate version lacked certificate reload support. | Corrected: reSIProcate 1.14.0 provides `SipStack::reloadCertificates()`. It marks secure transports for reload; later TLS-context access reloads certificate material. At the original review timestamp, the probe had not called or tested this API. Later 2026-10-04 supplements added SIGHUP-triggered reload and timed cert-swap smoke evidence in testbed scope; this supersedes that sentence as historical status only and does not change the conclusion that REQ-S-3 remains unverified. |
| S4 CANCEL flow could be read as proof that an ACK wire packet was independently captured. | README now identifies ACK as a protocol expectation, not a captured assertion. S4 reaches 487 and the expected callbacks, but the ACK packet was not independently captured. |

The transport seam implements policy matching for IP-only, IP:port (including bracketed IPv6 endpoints), and certificate-fingerprint tokens. It remains a pure seam; this review does not treat it as runtime transport or peer-identity enforcement.

## Follow-up Note (2026-10-04, signal/thread stop-flag race)

- A same-day follow-up review identified a real data race in `testbed/simulators/resip-probe/resip_probe.cxx`: `g_run` was a `volatile sig_atomic_t` written by both signal-handler and worker-thread paths.
- Intermediate fix state (historical): a dedicated signal-only stop request flag (`volatile std::sig_atomic_t g_stopRequested`) was introduced so the main loop could consume signal intent and store `g_run=false` outside signal context.
- Superseding final mechanism (current): `SIGINT`/`SIGTERM`/`SIGHUP` are blocked before worker creation and are drained in-process via timed `sigtimedwait` handling; `g_stopRequested` no longer exists in current code.
- Historical findings above are preserved as-is. No independent reviewer has re-run this review after applying this follow-up fix yet.

## Verification

- reSIProcate tag `resiprocate-1.14.0`, commit `632e215c2ca9aee5416bfe1808851ea6fa380044`, was cloned to `/tmp/as-resiprocate-m2-20261004`. CMake 3.31.12 and the required popt/c-ares packages were available after user-authorized system setup.
- Minimal native libraries built successfully with `cmake --build /tmp/as-resiprocate-m2-build-20261004 --parallel 4`; outputs included `libresip`, `libdum`, `librutil`, and `sipdialer`.
- The repository probe built in `/tmp/as-resiprocate-m2-probe-build`.
- S1 UDP completed 100/180/200/ACK/BYE/200 and exited cleanly.
- S1 TLS completed 100/180/200/ACK/BYE/200 and exited cleanly in an empty HOME after the local self-test trust initialization fix; no 503 occurred.
- The external TLS missing-cert/key negative run exited 1 before listener-port output.
- S4 UDP CANCEL reached 487. The ACK was not separately captured.
- `bash -n testbed/simulators/resip-probe/gen-cert.sh` and `git diff --check` passed.
- `uv run pytest -q platform/tests/test_transport_seam.py`: 23 passed. Ruff format/check and mypy passed for the platform SIP files.
- Full-repository `make gate` initial snapshot (earlier 2026-10-04 run) did not pass: Ruff check was blocked by the unrelated M4 `deploy/compose/scripts/m4b-8-seed-users.py` missing public docstring (D103). This review did not repair that unrelated issue.
- Full-repository `make gate` later rerun on 2026-10-04 passed after the M4 docstring fix: Ruff format reported 256 files already formatted; Ruff check passed; mypy reported 55 source files clean; pytest (`unit or contract`) reported 892 passed, 2 skipped, 165 deselected, 11 warnings.

## Residual Boundaries

- M2 remains open. The production platform transport binding/runtime adapter, TLS and peer-policy runtime wiring, and external S-SBC/operator PKI integration are not implemented or verified.
- The local TLS self-test trusts only the supplied self-signed certificate and only in non-external self-test mode. It does not demonstrate mTLS, production CA trust, REQ-S-2 acceptance, or peer whitelist enforcement at runtime.
- Although `SipStack::reloadCertificates()` exists, its runtime behavior is not verified here. Active-call preservation, new connections using the new certificate, and the old/new certificate overlap window required by REQ-S-3 remain untested and unaccepted.
- The reSIProcate native probe is testbed evidence, not the product adapter or M7 integration. S4's ACK wire packet also remains uncaptured.
- M6 remains paused pending M2 completion. M4 engineering is closed; that status does not close other acceptance gaps.
- No product acceptance, M2 completion, M7 start, or capacity result is claimed. REQ-S-1/2/3 acceptance remains open, and maintainer signoff is pending.

## Verification Supplement (2026-10-04, post-review evidence)

This supplement records additional evidence verified after the review above. It is not a new independent review and does not change the historical findings or conclusion.

- Probe launch: native `resip_probe --tls --external` started with the supplied local self-signed test cert/key and an empty HOME.
- External client check: separate `openssl s_client -connect 127.0.0.1:<random-port> -CAfile <cert.pem> -verify_return_error -verify_ip 127.0.0.1 -brief` completed successfully.
- Observed result: TLS 1.3 negotiated; certificate verification OK; CN `127.0.0.1`; temporary UAS then stopped.

Boundary of this supplement:

- This proves one external client-to-UAS TLS transport handshake only.
- It does not prove SIP INVITE exchange on that external connection.
- It does not prove S-SBC/operator PKI trust, mTLS peer allowlisting, certificate hot rotation behavior, or active-call preservation.
- It does not close REQ-S-2/REQ-S-3 acceptance, does not close M2, and does not alter M6 paused status or M4 state.

## Verification Supplement Addendum (2026-10-04, main-agent verified external transport)

This addendum records one additional transport-level check verified after the sections above. It does not replace findings or change review conclusions.

- Probe run: `resip_probe --tls --external` with temporary test cert/key under `/tmp`, printing dynamic TLS listener port `35619` for that run.
- Independent check: `openssl s_client -connect 127.0.0.1:35619 -CAfile /tmp/as-resiprocate-m2-tls-selftest-20261004/cert.pem -verify_return_error -verify_ip 127.0.0.1 -brief </dev/null`.
- Observed output: `CONNECTION ESTABLISHED`, `Protocol version: TLSv1.3`, `Verification: OK`, then `DONE`.

Scope boundary and impact:

- This is one external client-to-UAS TLS transport handshake only.
- It does not include SIP message exchange on that external connection.
- It does not verify S-SBC/operator PKI trust, mTLS peer allowlisting, certificate rotation behavior, or active-call preservation.
- It does not alter this review's conclusion and does not close M2 or REQ-S-2/REQ-S-3.

## Evidence Addendum (2026-10-04, main-agent verified external SIP transaction over TLS)

This addendum records one additional verified check after the transport-handshake supplements above. It does not rewrite findings or change this review's conclusion.

- Probe run: native `resip_probe --tls --external` started with local self-signed cert/key and temporary empty HOME, listening on a dynamic loopback TLS port.
- External client flow: `openssl s_client` connected with `-CAfile` trust and `-verify_ip 127.0.0.1`, then sent one raw SIP INVITE over TLS (`sips:` Request-URI with matching Via/Call-ID/CSeq/SDP fields).
- Probe-observed behavior: log shows the INVITE was received with `tlsd=127.0.0.1`; UAS returned `100 Trying`, `180 Ringing`, and `200 OK`.
- Dialog boundary: the OpenSSL client did not send ACK or BYE, so this is one external SIP transaction/early dialog response only, not a completed call/dialog.
- Repository impact: no repository code was changed for this raw SIP test; the temporary external UAS process was stopped after verification.

Scope boundary and impact:

- This extends evidence from transport handshake to one external SIP INVITE transaction over TLS with 100/180/200 responses.
- It does not verify S-SBC/operator PKI trust, mTLS peer identity/allowlisting, certificate hot rotation behavior, or active-call continuity.
- It does not close REQ-S-2/REQ-S-3 acceptance, does not close M2, and does not alter M6 paused status or M4 state.

## Verification Supplement (2026-10-04, timed testbed-only SIGHUP cert-swap smoke)

This supplement records one additional verification run after the sections above. It preserves the original findings and conclusion.

Scope and setup:

- Testbed-only native probe run after the nonblocking S1 hold change.
- One local loopback S1 call with `--tls --hold-ms 90000` and cert-A loaded at startup.
- During active hold, cert/key at the configured paths were atomically replaced with distinct cert-B, then `SIGHUP` was sent to the same probe PID.

Observed sequence and result:

- Log confirmed INVITE `200`/ACK and `S1 session established; BYE deadline scheduled`.
- Log order confirmed `SIGHUP received: invoking SipStack::reloadCertificates()` before `S1 hold deadline reached` and BYE.
- The existing dialog completed normal termination (`LocalBye` / `RemoteBye`), and the probe later exited normally after `SIGINT`.
- A new OpenSSL TLS connection to the same still-running probe verified successfully with cert-B as the only CA (`-CAfile`) and IP SAN verification `-verify_ip 127.0.0.1`, negotiating TLS 1.3.
- This indicates the post-reload new connection served cert-B in this scenario.

Non-claims and boundaries:

- No claim of operator PKI trust or external S-SBC integration.
- No claim of client certificate identity enforcement or mTLS policy acceptance.
- No claim of simultaneous old/new peer overlap window, dual-certificate acceptance, rollback, or multi-call behavior.
- No claim of production platform transport-adapter/runtime binding verification.
- No claim that REQ-S-2 or REQ-S-3 is satisfied; D8 remains open and M2 remains open.

Process note:

- No independent review of this supplement was run.

## Verification Supplement Addendum (2026-10-04, 90s hold cert-swap negative check clarification)

This addendum records one clarification tied to the same timed testbed-only cert-swap run noted above. It does not alter prior findings, scope boundaries, or conclusions.

- Positive check (already recorded): after in-process `SIGHUP` reload during active S1 hold, a new TLS handshake that trusted only cert-B verified successfully with TLS 1.3.
- Negative check (clarified here): in the same process state, a new TLS handshake that trusted only old cert-A failed verification with `self signed certificate`.
- Evidence selection note: one earlier short-hold (15/20s) attempt had `SIGHUP` after BYE and is explicitly excluded from evidence; the accepted evidence run is the 90-second hold log.

Boundary and process note:

- This is still partial, testbed-only evidence and not REQ-S-3 acceptance.
- No new independent review of this addendum was run.

## Verification Supplement (2026-10-04, non-external TLS S2/S3/S4 smoke)

This supplement records one additional same-day evidence set verified after the sections above. It does not rewrite historical findings or alter the overall conclusion.

- Scope: native `resip_probe --tls` self-test mode only (non-external), using the local self-signed cert/key and loopback `sips:127.0.0.1` trust path.
- S2 result: returned `404 Not Found` and exited normally (`probe 退出 OK`).
- S3 result: returned `603 Decline` and exited normally (`probe 退出 OK`).
- S4 result: UAC sent `CANCEL`; logs showed `RemoteCancel`/`LocalCancel` callbacks and the `487` response path before normal exit (`probe 退出 OK`).
- Evidence caveat: ACK wire message for S4 was not independently captured; this supplement does not claim an ACK packet capture.

Boundary and impact:

- These are loopback testbed/protocol-stack smoke checks, not product transport-adapter/runtime binding verification.
- They do not prove external S-SBC/operator PKI trust, mTLS peer allowlisting, full E1/E4 acceptance, REQ-S-2/REQ-S-3 acceptance, capacity evidence, or M2 completion.
- M6 paused status and M4 closed status are unchanged.

## Corrective Supplement (2026-10-04, TLS Contact Routing Correction)

This supplement records a correctness correction after the sections above. It preserves the original findings/conclusion and narrows evidence eligibility for active-call cert-swap claims.

- Historical correction: earlier active-call A/B reload notes predated the TLS Contact routing fix. At that time, TLS-mode master-profile Contact pointed to the UDP listener port, so those runs do not prove BYE stayed on TLS for the in-flight dialog.
- Evidence status change: those pre-fix runs are superseded and are excluded from full TLS in-flight active-call preservation evidence.
- Valid current run: `probe-full-tls-rotation.log` (90-second hold, same process, no restart) starts with cert-A, performs atomic cert/key swap to cert-B during active hold, and sends `SIGHUP`.
- Log ordering: `SIGHUP received: invoking SipStack::reloadCertificates()` appears before hold deadline and BYE.
- TLS BYE marker: the UAS BYE-receive line includes `tlsd=127.0.0.1`, and BYE Request-URI/Contact point to the TLS listener port (`sips:` Contact), then `LocalBye`/`RemoteBye` and `probe 退出 OK`.
- Post-reload cert checks: a new OpenSSL client trusting only cert-B completes TLS 1.3 with IP SAN verification, while a client trusting only old cert-A fails verification (`self signed certificate`).

Limitations (unchanged):

- This remains one local self-signed testbed scenario.
- It does not establish dual-certificate overlap window behavior, operator PKI/mTLS, external S-SBC integration, production platform binding/runtime wiring, concurrent multi-call behavior, rollback semantics, or full REQ-S-3 acceptance.
- M2 remains open; REQ-S-2/REQ-S-3 remain unaccepted; M6 paused and M4 closed statuses are unchanged.

Process note:

- This corrective supplement/addendum was not independently re-reviewed.

## Verification Supplement - full make gate rerun (2026-10-04)

This supplement preserves the original failed-attempt history in the Verification section. That earlier local `make gate` stop at D103 in `deploy/compose/scripts/m4b-8-seed-users.py` (missing public docstring) was later superseded by a same-day local rerun after the maintainer-authorized docstring fix.

Local rerun result (2026-10-04, non-CI):

- Ruff format: 256 files already formatted.
- Ruff check: all checks passed.
- mypy: 55 source files clean.
- `pytest -m "unit or contract" -q`: 892 passed, 2 skipped, 165 deselected, 11 warnings.

Status impact:

- This improves repository local gate status for the reviewed snapshot.
- It is a local gate result only and is not a CI claim.
- It does not close M2.
- It does not close REQ-S-2 or REQ-S-3.
- It does not close D8.
- It does not constitute product acceptance.