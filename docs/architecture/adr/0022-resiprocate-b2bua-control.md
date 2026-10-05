# ADR-0022: reSIProcate B2BUA control layer

- **Status**: accepted
- **Date**: 2026-09-30
- **Amended**: 2026-10-05 — M2 product ingress/runtime (`ResipRuntimeListener`, ingress gate, `decide()` on the product UDP/TLS path) exists; **product `CallController` implementation begins in the M7 engineering slice** (`platform/src/as_platform/sip/call_controller.py`). Acceptance does **not** close D10, REQ-NF-1, D9 adapter API selection, or full E1.
- **Decides**: §0 ledger item 8 — use reSIProcate `SipStack` for transport and transaction processing, DUM above it for UA dialog/`InviteSession` and session-level behavior, and add a product `CallController` above DUM for cross-leg B2BUA business control.
- **回应 REQ**: REQ-F-1–REQ-F-5, REQ-F-8–REQ-F-11, REQ-NF-1–REQ-NF-4

## Context（背景）

ADR-0019 accepted reSIProcate C++ as the production SIP stack. That choice remains in force. A SIP stack is not, by itself, the product's complete B2BUA call-control policy: the product must correlate an inbound UAS leg and an independent outbound UAC leg, make application decisions, and coordinate their business lifecycle.

Existing requirements already define the required behavior: distinct legs and Call-IDs, Request-URI and SDP handling, Route/Record-Route, CANCEL/BYE, in-dialog requests, non-2xx responses, and cancellation/final-response races (REQ-F-1–REQ-F-5, REQ-F-8–REQ-F-11). This ADR assigns responsibilities; it does not claim those behaviors are implemented or accepted.

The upstream reSIProcate 1.14.0 source was checked at tag commit `632e215c2ca9aee5416bfe1808851ea6fa380044`. `BUILD_PYTHON=ON` enables PyCXX-based rePro Python routing/plugin targets; it does not provide a general `resip`/DUM Python module. In the current E1 harness, `import resip` exits 2. A native C++ resip-probe built against this source completed local self-loop S1 and S4 smoke runs with exit 0, including INVITE/180/200/ACK/BYE and CANCEL/487. These are native DUM smoke checks, not product E1 or acceptance evidence. Native TLS S1 did not establish a call: it returned 503 Certificate Validation Failure and timed out with exit 124. E4 remains unverified.

There is a state-recovery conflict that must remain visible. ADR-0002 says session/dialog state is externalized, and REQ-NF-1 requires a process restart not to drop active calls. While a process is running, `SipStack` owns transport and transaction-processing runtime, including transaction timers; DUM is a `TransactionUser` and UA/session layer using `SipStack`, with dialog, `InviteSession`, and session-level behavior. Those runtime objects are not thereby Redis-serializable. The product `CallController` owns the semantic cross-leg mapping and recoverable business context. No evidence currently proves process-restart reconstruction of either `SipStack` transaction runtime or DUM dialog/session runtime. ADR-0019 E5 is unverified.

Exploratory D9 probes now demonstrate a narrow in-process route: a native extension can call Python on native caller/worker threads; a real UDP UAS `onNewSession` path calls the existing Python `decide()` and returns 404 (or 500 on the injected exception path); a separate two-leg probe forwards a downstream 486 to the inbound leg. These prove bridge feasibility only. They do not define a product adapter API or cover forking, final-response races, or full E1. The Python bridge spike is not a general upstream DUM binding.

D10 recovery probes are asymmetric. A two-process UAC `DialogSetId` recreation hook sent an in-dialog re-INVITE under the same Call-ID/tags and received 200 after manually restoring To-tag, Route, remote target, and CSeq. It did not restore the old `InviteSession`, transaction, or active media/call state. In a separate UAS test, a fresh DUM received a correctly formed same-dialog BYE after the prior process exited and returned 481. Source inspection found the missing `DialogSetId` in DUM's private dialog-set map and no public UAS dialog/session rehydrate API. This does not prove a custom DUM extension impossible, but default DUM fails this restart case; `SipStack` transaction recovery and product cross-leg mapping remain unproven. D10 is not passed / unresolved, and REQ-NF-1 remains hard.

Bounded D11 native DUM wire comparisons passed for 143- and 233-byte valid offers, the 230-byte S1 offer, and one distinct 238-byte answer. The distinct answer was byte-identical across the tested legs and differed from the offer. This limited sample is feasibility evidence only, not full product-path or REQ-F-4 acceptance.

## Decision（决策）

Use reSIProcate's `SipStack` and DUM as the SIP protocol and UA/session layers, respectively, and add a dedicated logical product `CallController` above DUM. `SipStack` owns transports, transaction processing, transaction timers, and the process loop. DUM is a `TransactionUser`/UA layer that uses `SipStack` and owns dialog, `InviteSession`, and session-level behavior, including its supported session timers. The controller must not duplicate stack transactions, retransmission, or timers.

The `CallController` is responsible for correlating the independent inbound UAS and outbound UAC legs and their distinct Call-IDs; mapping DUM session events to business decisions and outbound commands; coordinating provisional and final responses, CANCEL/BYE, in-dialog requests, non-2xx outcomes, race resolution, and cleanup; and invoking the existing pure Python decision modules. It must preserve the required Request-URI, SDP, Route/Record-Route, and two-leg semantics. DUM callbacks must remain nonblocking, consistent with `AGENT.md`.

The product language decision remains Python; this ADR does not migrate business applications. It does not choose a production Python/C++ API. D9 feasibility evidence exists, but the product bridge/adapter boundary remains unselected and the probes do not cover full E1, forks, or final-response races; maintainer review and implementation authorization are still required. D10's design-gap review is **not passed / unresolved** because the default-DUM UAS restart test returns 481. The maintainer must decide between a custom UAS recovery mechanism/extension with transaction-behavior proof and a formal ADR/design review of the product architecture. No workaround is accepted here, and REQ-NF-1 is not weakened.

ADR-0019's production stack selection is unaffected. This ADR does not authorize code start, declare K2 released, or authorize K2/release acceptance.

## Consequences（后果）

### Positive（正面）

- Separates SIP protocol machinery from product cross-leg decisions and makes the B2BUA control responsibilities reviewable.
- Reuses the existing Python decision modules without moving product business policy into DUM callbacks.
- Keeps transaction retransmission and timer correctness in the SIP stack rather than duplicating it in product code.

### Negative / accepted（负面 / 已接受）

- The native bridge and DUM→Python feasibility path have exploratory evidence, but no production bridge API, product adapter, or complete E1 implementation is established. Product integration remains blocked pending maintainer review and authorization.
- The controller's recoverable business context, `SipStack` transaction runtime, and DUM dialog/session runtime have different ownership and persistence properties. A narrow UAC recreation hook is not UAS or transaction recovery; the default-DUM UAS restart test returns 481. REQ-NF-1 remains a hard acceptance requirement; D10/E5 is not passed / unresolved and blocks acceptance.
- Limited native DUM SDP body comparisons passed, including a distinct answer, but the product adapter and broader corpus remain untested. REQ-F-4 is not accepted or declared met.
- Native S1/S4 smoke evidence does not establish product E1, E4, or requirement acceptance. The TLS S1 failure and missing `resip` module remain open evidence gaps.
- The logical `CallController` design does not imply that its implementation exists or that K2 may start.

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| Treat DUM alone as the complete product B2BUA | DUM supplies SIP mechanisms, not the product's semantic cross-leg mapping and business decision coordination. |
| Put transaction timers and retransmission in `CallController` | Duplicates stack-owned SIP behavior and creates competing protocol state machines. |
| Select the Python/C++ bridge in this ADR | Build/source evidence establishes that the assumed general Python binding is absent, but does not yet compare viable integration approaches sufficiently. The spike is a blocking prerequisite. |

## Evidence（证据）

- Upstream tag `1.14.0`, commit `632e215c2ca9aee5416bfe1808851ea6fa380044`; source inspection confirmed `BUILD_PYTHON=ON` does not build a general DUM Python module.
- E1 Python harness with explicit port: `import resip` failed and exited 2.
- Native C++ resip-probe local self-loop S1 and S4: exit 0; S1 exercised INVITE/180/200/ACK/BYE and S4 exercised CANCEL/487. This is native stack smoke only, not product E1 or acceptance.
- Native TLS S1: 503 Certificate Validation Failure; call not established; timeout exit 124. E4 remains unverified.
- Build products and logs are outside the repository under `/tmp/as-resiprocate-userbuild`.
- D9 primitive CPython callback results: `/tmp/as-resip-python-bridge-spike/RESULTS.md`; real DUM→Python 404/500: `/tmp/as-resip-dum-python-slice/RESULTS.md`; one two-leg 486: `/tmp/as-resip-dum-two-leg-spike/RESULTS.md`. These are isolated spikes, not a product binding or adapter.
- D9 isolated early-CANCEL branch: `/tmp/as-resip-dum-final-probes/logs/probe-b-final-isolated.log`; it covers one early branch only, not final-response races or forking.
- D10 UAC DialogSet recreation hook: `/tmp/as-resip-dum-process-restart/RESULTS.md`; D10 default-DUM UAS restart returning 481: `/tmp/as-resip-dum-uas-restart/RESULTS.md`. No old UAS session/transaction or controller mapping was recovered; no public UAS rehydrate API was found.
- Bounded D11 offer/body probe: `/tmp/as-resip-dum-sdp-spike/RESULTS.md`; initial S1 roundtrip: `/tmp/as-resip-dum-sdp-roundtrip/RESULTS.md`; distinct-answer and CANCEL probes: `/tmp/as-resip-dum-final-probes/logs/probe-a-final.log` and `probe-b-final-isolated.log`. These do not constitute complete product REQ-F-4 acceptance.
- Source inspection of reSIProcate layering and DUM cancellation semantics: `DialogUsageManager` is a `TransactionUser`, is constructed with and holds a `SipStack&`, and exposes `getSipStack()`; `SipStack` owns transports, transaction processing, timers, and its process loop. DUM provides UA/dialog/`InviteSession` and session-level behavior over that stack. `ServerInviteSession` has no `cancel()` method and `InviteSessionHandler` has no `onCancel` virtual. For an inbound initial UAS INVITE CANCEL, DUM sends 200 to CANCEL and 487 to INVITE on that leg and reports `onTerminated(... RemoteCancel ...)`; the product controller must still coordinate the opposite UAC leg and race/cleanup semantics. `InviteSession::end()` means BYE, including the early-state `ClientInviteSession::end()` path in this version; selecting a cancellation API is contingent on the D9 adapter spike and race tests. DUM has RFC session-timer support; transaction timers/retransmissions belong to `SipStack`. `makeInviteSession(...)` returns a message to send; handles are delivered through DUM callbacks. These facts inform responsibility boundaries and do not prescribe a product API.
- Bounded native DUM wire comparisons now show byte identity for three tested offer forms (230/143/233 bytes) and one distinct 238-byte answer. This does not cover the complete product adapter, broad boundary corpus, or all required routes; REQ-F-4 remains unaccepted until that evidence is reviewed.

## Related（相关）

- [ADR-0019](0019-sip-stack-selection.md) — accepted production stack selection; unchanged.
- [ADR-0002](0002-per-usecase-process-state-redis.md) — process/state model; recovery contradiction remains open.
- [`../新系统整体架构.md`](../新系统整体架构.md) §0 and §10.
- [`../../requirements/prd.md`](../../requirements/prd.md) — referenced functional and non-functional requirements.
- [`../../plan.md`](../../plan.md) §5 — integration and recovery blockers.