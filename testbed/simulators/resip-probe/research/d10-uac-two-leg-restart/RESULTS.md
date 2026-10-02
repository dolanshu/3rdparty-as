# D10 Two-Leg Cross-Process Spike Results

## Prior Attempts

- `20260930T231312464107869Z` completed Phase A for both legs and reaped Phase A before Phase B. Leg-a sent a correlated CSeq-2 re-INVITE and received a real correlated 200, but the child then reported `DUM received final failure status 200`; the parent stopped before ACK or leg-b. The archived log does not expose the underlying exception.
- `20260930T231710523535157Z` reached the same Phase-B leg-a 200 and then logged `onConnected callback threw reSIProcate BaseException: Missing header Record-Route`; the child exited before ACK or leg-b.
- The direct failure was in the temporary callback assertion, not SIP correlation: it inspected an optional Phase-B response header that the fake peer correctly omitted. In reSIProcate 1.14.0 `Dialog::dispatch`, a 2xx without Record-Route falls back to the restored outbound request's Route set when that request has a To-tag and Route headers. Both previous run directories and logs are preserved.

## Harness Changes

- Removed the Phase-B callback's Record-Route dereference. Parent 200 validation accepts an absent Record-Route and, if present, checks it against the saved Route set.
- Kept the strict ACK validation and explicitly recorded that each Phase-B ACK retained the exact saved Route set. Call-ID, From/To tags, CSeq, Request-URI/target, snapshot, ACK, and business-token checks remain enabled.
- Added socket-bound assertions at the Phase-A and Phase-B boundaries and port overrides for isolated runs.

## Fresh Run

Artifact: `/tmp/as-resip-two-leg-restart-recovery/runs/20260930T232818798475278Z`

Command and outcome:

```sh
CLIENT_PORT=53781 PEER_A_PORT=53782 PEER_B_PORT=53783 \
  bash /tmp/as-resip-two-leg-restart-recovery/run.sh
```

Overall exit code: `0`. All run stages returned `0`, including shell syntax, Python syntax, native build, extension import, two-process harness, final status capture, and byte-for-byte status comparison. The native build and `ldd` check also passed independently: build `0`, `ldd` `0`, dependency check `0`; all five expected libraries resolved (`libdum-1.14`, `libresip-1.14`, `librutil-1.14`, `libresipares-1.14`, `libpython3.10`).

| Leg | Call-ID | Local tag / remote To-tag | Phase A | Phase B | Target and retained Route set |
|---|---|---|---|---|---|
| leg-a | `WZubNnhVuaiGFV9umBn-EQ..` | `3dc45f48` / `uas-leg-a-restart-stable-tag` | Initial INVITE CSeq 1; 200 and ACK confirmed | Same Call-ID/tags, in-dialog re-INVITE CSeq 2; correlated 200 and ACK CSeq 2 confirmed; 200 had no Record-Route | Target `sip:uas-leg-a@127.0.0.1:53782;transport=udp`; ACK Route `sip:127.0.0.1:53782;lr;transport=udp` |
| leg-b | `zhS_K-E2yz7RI2XnXx48bQ..` | `840472bb` / `uas-leg-b-restart-stable-tag` | Initial INVITE CSeq 1; 200 and ACK confirmed | Same Call-ID/tags, in-dialog re-INVITE CSeq 2; correlated 200 and ACK CSeq 2 confirmed; 200 had no Record-Route | Target `sip:uas-leg-b@127.0.0.1:53783;transport=udp`; ACK Route `sip:127.0.0.1:53783;lr;transport=udp` |

Phase B ran sequentially, leg-a then leg-b. For each re-INVITE, the parent matched the saved Phase-A DialogSetId, local and remote tags, target, CSeq increment, and Route set; the wire ACK then matched that same Route set. Both callbacks associated the leg with the expected business token.

## Process and Peer Lifecycle

- Phase-A PID `178399` exited `0` and was absent from `/proc` before Phase B started. Phase-B PID `178403` exited `0` and was also absent after reaping.
- Fake-peer sockets on `53782` and `53783` were confirmed bound after Phase-A ACKs, before Phase B, and after Phase B. They remained open through both phases and were closed in final cleanup. The earlier `peer_sockets_kept_bound_through_both_phases: false` reflected Phase B aborting before success metadata was set; inspection found no premature close. The new run records all boundary checks as true.
- Repository status after the run is byte-for-byte identical to `/tmp/as-resip-two-leg-restart-recovery/git-status.initial`; no repository files or docs were changed.

## Limits

This spike proves only UAC `DialogSetId` re-INVITE re-association into a new process, including fallback to the supplied outbound Route set. It does not prove restoration of the original DUM `InviteSession` or transactions, UAS state recovery, pending-transaction behavior, races or forks, or REQ-NF-1 globally.