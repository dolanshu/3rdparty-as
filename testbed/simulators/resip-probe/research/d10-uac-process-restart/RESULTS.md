# reSIProcate DUM Process-Restart Probe

Run started: `2026-09-30T18:59:03Z`  
Result: **PASS** for the narrow UAC `DialogSetId` re-INVITE recreation route.

## Environment

- reSIProcate source: version 1.14.0, commit `632e215c2ca9aee5416bfe1808851ea6fa380044`
- Existing build: `/tmp/as-resiprocate-userbuild/upstream-minimal-20260930`
- Source checkout had a pre-existing untracked `UILD_RECON=OFF/version.h`; it was not modified.
- Python: existing uv-selected workspace CPython 3.10.21 at `/home/shudong/project/3rdparty-as/.venv/bin/python`
- Peer: parent Python process, `127.0.0.1:39841`; DUM transport in each child: `127.0.0.1:39842`
- Parent peer socket was bound before phase A and remained bound through phase B. Each child had a 12-second parent deadline; the DUM child loop deadline is 8 seconds.

## Result

The parent Python process (PID 149191) retained the fake UAS UDP socket and ran both peer exchanges. Phase A ran in child PID 149192; phase B ran in a distinct child PID 149195. `wait()` reaped PID 149192 with exit code 0, and `/proc/149192` was absent before phase B was started. Phase B then exited 0 and was reaped; `/proc/149195` was absent afterward. The event ordering and monotonic timestamps are in `process-lifecycle.json` and the individual exit records are under `processes/`.

Each child constructed its own `SipStack` and `DialogUsageManager`, bound the same client port in sequence, and serviced `stack.process()`/`dum.process()` on its main thread. Each child logged exactly one `onConnected` callback with status 200, and each callback verified it ran on that child’s DUM loop thread. No session handle or process pointer was serialized or passed across the restart.

Phase A sent an initial INVITE at CSeq 1. The parent peer returned 200 with stable remote To-tag `uas-process-restart-stable-tag`, Contact `sip:uas@127.0.0.1:39841;transport=udp`, and Record-Route `sip:127.0.0.1:39841;lr;transport=udp`. DUM sent ACK at CSeq 1.

`state.json` persisted the phase-A restore inputs: `DialogSetId` Call-ID `T1zuZZbT9WJj8kVq43oEvg..` and local tag `827aa09d`, remote To-tag `uas-process-restart-stable-tag`, remote target Contact, route set, last CSeq 1, and business context key `as-call-process-restart-2026-09-30`.

Phase B loaded that JSON and called the 1.14.0 overload:

```cpp
dum.makeInviteSession(target, dialogSetId, profile, &offer,
                       resip::DialogUsageManager::None);
```

The returned `SipMessage` was then edited before `dum.send()` to set `To`'s `p_tag` from the saved remote To-tag, append the saved route-set entries to `h_Routes`, and set `h_CSeq.sequence()` to `last_cseq + 1`. The child checked the Call-ID, From-tag, To-tag, CSeq, and Route count in memory before sending. The peer independently checked decoded wire fields against the retained phase-A JSON identity and returns 481 when those checks find mismatches; missing or malformed required headers fail the harness rather than being accepted as a dialog. It never treats an untagged/new initial INVITE as a restored dialog.

The captured phase-B request had the same Call-ID and both tags, Request-URI equal to the saved remote Contact, the saved Route, and CSeq 2. The peer returned 200 with those same dialog tags and correlated CSeq 2, deliberately without Record-Route. DUM sent ACK at CSeq 2 with the saved Route, and phase B received `onConnected(200)`. This also demonstrates the documented response-time Route fallback with the Route supplied on the restored request.

The six exact UDP SIP datagrams are saved as `messages/phase-a-001-child-to-peer-invite.sip` through `messages/phase-b-006-child-to-peer-ack.sip`; their ordered metadata is in `wire-events.jsonl`.

## Source Interpretation

In this exact source revision, the `DialogSetId` overload constructs a new `InviteSessionCreator`, sets only Call-ID and From-tag, then creates a new session (`resip/dum/DialogUsageManager.cxx`, around lines 602-615). It does not deserialize or recover a prior Dialog, InviteSession, transaction, route set, remote target, or CSeq history. The application supplied the To-tag, Route, target, and incremented CSeq described above. This is dialog recreation using DUM’s documented hook, not transaction or live-session restoration.

The child logs include the normal DUM shutdown warning that client transaction states remain during stack destruction. Both processes still exited with status 0 after completing their exchanges; this is not evidence of graceful transaction persistence.

## Commands And Exit Codes

Focused checks and run:

- `/home/shudong/project/3rdparty-as/.venv/bin/python -m py_compile /tmp/as-resip-dum-process-restart/process_restart.py` — 0
- `bash -n /tmp/as-resip-dum-process-restart/run.sh` — 0
- `bash /tmp/as-resip-dum-process-restart/run.sh` — 0
- Child C++ build inside `run.sh` — 0
- `ldd /tmp/as-resip-dum-process-restart/dum_phase_child` validation — 0; all reSIProcate libraries resolved, no `not found`
- Parent process-restart harness on ports 39841/39842 with 12-second timeout — 0
- Before/after repository status capture — both commands 0, identical content
- Regular-file SHA-256 manifest comparison excluding `.git` — 0, `BYTE_FOR_BYTE_IDENTICAL`
- Before/after repository symlink comparison — 0, identical

`commands.log` contains the exact build, runtime, and comparison invocations. `exit-codes.txt` records the run’s command statuses. `repo-status-before.txt`, `repo-status-after.txt`, both SHA-256 manifests, and the symlink snapshots preserve the repository baseline evidence. The repository already had unrelated modifications and untracked documentation at the start; the final status is unchanged from that baseline.

No `sudo`, package/system installation, commit, push, tag, or branch operation was used. Failure handling is strict and preserves logs, raw messages, process records, and `failures.json`; this run had no timeout or SIP mismatch, and no artificial failure was injected.

## Limits

This establishes only the UAC `DialogSetId` re-INVITE recreation route using application-reconstructed wire state. It does **not** prove UAS-leg recovery, full two-leg mapping recovery, in-flight transaction restoration, media recovery, global REQ-NF-1, E1/E4/E5 closure, D10 closure, or K2 release. It is not a release or acceptance-gate closure claim.
