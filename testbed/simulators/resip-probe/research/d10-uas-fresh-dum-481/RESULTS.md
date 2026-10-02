# Bounded UAS DUM Restart Experiment

Run: 2026-09-30 19:12:28 UTC (wire-event timestamps; local date was 2026-10-01)  
Outcome: **PASS for the narrow default UAS restart behavior**. A fresh reSIProcate 1.14.0 DUM returned the actual `481 Call/Transaction Does Not Exist` response to an in-dialog BYE after the prior process exited. This is not final REQ-NF-1 acceptance and does not show that custom recovery is impossible.

## Scope And Environment

- All experiment-created files are under `/tmp/as-resip-dum-uas-restart/`.
- Existing reSIProcate source: `/tmp/as-resiprocate-userbuild/resiprocate-1.14.0`, commit `632e215c2ca9aee5416bfe1808851ea6fa380044`.
- Existing build: `/tmp/as-resiprocate-userbuild/upstream-minimal-20260930`.
- Runtime: CPython 3.10.21 at `/home/shudong/project/3rdparty-as/.venv/bin/python`; native harness compiled with the preinstalled C++ compiler and existing libraries. No package/system install was run.
- Explicit UDP ports: DUM `127.0.0.1:47771`, harness peer `127.0.0.1:47772`. Both were bind-preflighted as available. The peer socket remained bound across both phases. Harness I/O waits were bounded at 8 seconds; child lifetime was bounded at 14 seconds.
- The C++ child constructs the same `SipStack`, `DialogUsageManager`, profile, invite handler, and loopback UDP transport in each phase. Phase B receives no state arguments and does not access or seed DUM internals. The Python harness retains Phase-A state in `state.json` but does not pass it to the child.

## Phase A: Establish A Real UAS Dialog

The peer sent an initial INVITE with a valid PCMU SDP offer (CSeq `1 INVITE`), caller Contact, and one Record-Route URI pointing to the loopback DUM listener. DUM returned `180 Ringing`, then `200 OK` with an SDP answer, Contact, and the same Record-Route. The peer sent ACK using the response Contact and route set.

Captured identity and routing state:

- Call-ID: `uas-restart-62cd7ef4763c4c14@127.0.0.1`
- Caller From-tag: `caller-62cd7ef4763c4c14`
- AS To-tag: `3487f79b`
- AS Contact / remote target: `sip:uas@127.0.0.1:47771`
- Caller route set: `sip:127.0.0.1:47771;lr;transport=udp`
- Phase-A INVITE CSeq: `1`; saved next CSeq: `2`

DUM logged `CALLBACK UAS_CONNECTED status=200`, then, after processing ACK, `CALLBACK UAS_CONNECTED_CONFIRMED cseq=1`. Phase-A PID `151367` exited normally with code `0`; `wait()` reaped it and `/proc/151367` was absent before Phase B started.

## Phase B: Fresh DUM, No Restored Dialog

A distinct process (PID `151368`) created a new `SipStack` and DUM on the same `127.0.0.1:47771` port with the same profile/handler/transport setup. No Dialog, DialogSet, InviteSession, or Phase-A application state was restored or pre-seeded. The peer sent a BYE with:

- Same Call-ID and caller From-tag / AS To-tag
- Request-URI equal to the saved AS Contact: `sip:uas@127.0.0.1:47771`
- Route header equal to the saved route set, sent to that route's loopback next hop
- Caller Contact from Phase A
- Incremented `CSeq: 2 BYE`

The captured response, received from `127.0.0.1:47771`, was exactly:

`SIP/2.0 481 Call/Transaction Does Not Exist`

The response matched the BYE Call-ID, both tags, and `2 BYE`. The harness did not synthesize any response. DUM's own Phase-B log says `Rejected request (which was in a dialog)` at `DialogUsageManager.cxx:2095`. Phase-B then handled SIGTERM through its signal handler, exited code `0`, was reaped, and had no remaining `/proc` entry.

## Raw Datagrams And State

The following files contain the complete captured UDP SIP datagrams, byte-for-byte as sent or received. Ordered metadata, timestamps, source/destination addresses, and sizes are in `wire-events.jsonl`.

| Sequence | Datagram | Bytes |
|---|---|---:|
| 1 | `messages/phase-a-001-peer-to-dum-invite-invite.sip` | 631 |
| 2 | `messages/phase-a-002-dum-to-peer-response-180.sip` | 390 |
| 3 | `messages/phase-a-003-dum-to-peer-response-200.sip` | 627 |
| 4 | `messages/phase-a-004-peer-to-dum-ack-ack.sip` | 369 |
| 5 | `messages/phase-b-005-peer-to-dum-bye-bye.sip` | 422 |
| 6 | `messages/phase-b-006-dum-to-peer-response-481.sip` | 339 |

`state.json` is the harness-retained Phase-A snapshot. Process commands/exits are in `processes/`; checks and assertions are in `validation.json`, `validation.txt`, and `failures.json`. DUM logs are `logs/phase_a-dum.log` and `logs/phase_b-dum.log`; build, dependency, and driver logs are in `logs/`.

## Source And Public API Inspection

For an external in-dialog request, `DialogSetId` uses Call-ID and the request's To-tag as the local tag (`resip/dum/DialogSetId.cxx:12`, `:26`). `DialogUsageManager::processRequest` sees the To-tag, calls `findDialogSet(DialogSetId(request))` (`resip/dum/DialogUsageManager.cxx:2072`, `:2087`), and responds with 481 for a non-ACK request when the map lookup returns no DialogSet (`:2093`). `findDialogSet` searches `mDialogSetMap` and returns null when the key is absent (`:2373`, `:2377`). In a fresh DUM process that map has no Phase-A UAS DialogSet; the observed wire response and DUM log match this path.

No public API to import or rehydrate an existing UAS Dialog/ServerInviteSession was found in the 1.14.0 DUM headers/source inspected. The map and `findDialogSet` are private (`DialogUsageManager.hxx:464`, `:504-505`); public `findAppDialogSet` and `findInviteSession` methods are lookups (`:302`, `:304`). `ServerInviteSession` exposes operations on a live session, while its constructor is private to DUM/`Dialog` (`ServerInviteSession.hxx:115`). The public `makeInviteSession(..., DialogSetId, ...)` overload is a distinct client-side path: its implementation creates an `InviteSessionCreator` and outbound session (`DialogUsageManager.hxx:204`, `DialogUsageManager.cxx:602`, `:612`). `Dialog.cxx:742-745` describes its dialog-recovery route-set behavior for an outbound client dialog. It is not UAS state rehydration.

This is a statement about default DUM behavior and the inspected public API, not a claim that an adapter or future design cannot reconstruct dialog context by other means. A recovery adapter could persist sufficient call/dialog context and implement an explicit reconstruction or routing strategy; that design was not tested here.

## Commands, Exit Codes, And Repository Guard

Reproducible runner: `bash /tmp/as-resip-dum-uas-restart/run.sh` returned `0`. Exact build, `ldd`, and harness invocations are in `commands.log`; their statuses are in `exit-codes.txt`:

- reSIProcate source commit query: `0`
- CPython version query: `0`
- Native C++ build: `0`
- `ldd` dependency validation (no `not found`): `0`
- Two-phase harness: `0`
- Final `git status --short` capture: `0`
- Initial/final status `cmp`: `0`, `repo-status-comparison.txt` says `IDENTICAL`

The repository already had unrelated modified and untracked paths at the initial snapshot. `repo-status-initial.txt` and `repo-status-final.txt` preserve those same entries. No repository file was edited by this experiment. No sudo, apt, system installation, commit, push, tag, or branch operation was used.

## Caveats And Limits

Both DUM process logs contain the shutdown warning `On shutdown, there are Server TransactionStates remaining!`. Phase A nevertheless returned normally only after ACK confirmation, exited with code `0`, and its PID was verified gone. The warning means transaction-state drainage at process teardown was not established; this was not a DUM graceful-shutdown/persistence test.

The experiment covers one established UAS dialog over loopback UDP. Its Record-Route is a loopback route back to the DUM listener; no independent SIP proxy, RTP/media flow, retransmission/loss behavior, TLS, forked dialogs, in-flight transaction restoration, B2BUA leg mapping, or broader acceptance gate was tested. It establishes the default fresh-DUM UAS result only: the observed response is 481 when no matching UAS DialogSet is present in the restarted DUM.
