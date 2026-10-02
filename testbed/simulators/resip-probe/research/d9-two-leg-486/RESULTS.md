# Native DUM + Python Two-Leg Failure-Path Spike

Date: 2026-09-30

Status: **PASS for this throwaway D9 feasibility slice only.** This is not a product adapter, approved API, full B2BUA result, or release/acceptance evidence.

## Result

The uv CPython 3.10.21 extension compiled and linked against the supplied reSIProcate 1.14.0 build. A real UDP INVITE entered DUM, crossed to the repository's Python `decide()` function, and produced a DUM-generated outbound UAC INVITE to the rule's exact target. The local UDP peer returned a matching final 486. DUM's real UAC `onFailure` callback correlated the generated outbound Call-ID to the saved inbound UAS handle, rejected that inbound leg with 486, and the Python test client received the 486 with the original Call-ID and CSeq.

All DUM/SipStack/session state stayed on one native DUM event-loop thread. The Python callback acquired the GIL on that same thread and received only scalar strings. DUM also emitted the downstream non-2xx ACK; the test client sent and saved an upstream non-2xx ACK.

## Environment And Ports

- Source/build: `/tmp/as-resiprocate-userbuild/resiprocate-1.14.0` and `/tmp/as-resiprocate-userbuild/upstream-minimal-20260930` (reSIProcate 1.14.0).
- Python ABI: uv CPython 3.10.21, `cpython-310-x86_64-linux-gnu`, suffix `.cpython-310-x86_64-linux-gnu.so`.
- Python include: `/home/shudong/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/include/python3.10`.
- Python library: `/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib/libpython3.10.so.1.0`.
- Compiler: `/usr/bin/c++`, GCC 9.4.0.
- Ports were configurable with `SPIKE_UAS_PORT`, `SPIKE_UPSTREAM_PORT`, and `SPIKE_DOWNSTREAM_PORT`. The final run explicitly used UAS `127.0.0.1:43761`, upstream client `127.0.0.1:43762`, and downstream peer `127.0.0.1:43763`. A preflight bound all three simultaneously and confirmed they were free before launch; the test then bound the two peer sockets and DUM bound the UAS port.

## Final Run Evidence

- Inbound Call-ID: `two-leg-in-805d93d9-a90f-4b62-93bb-1e38cc762d6a@127.0.0.1`.
- Generated outbound Call-ID: `cmDGS05NhA3fKX_l6lC4dA..`.
- The identifiers differ; the downstream peer recorded the outbound Call-ID from the actual wire INVITE.
- Python callback inputs were calling number `+15551230001` and called number `+15558675309`.
- `decide()` matched rule `two-leg-forward`, action `forward`, and target `sip:+15559990002@127.0.0.1:43763;transport=udp`.
- Outbound Request-URI exactly matched that target URI.
- Downstream peer returned `SIP/2.0 486 Busy Here`, copying Via, From, Call-ID, and CSeq from the outbound INVITE and adding a To tag.
- DUM's UAC `onFailure` observed status 486 and mapped it to upstream status 486 on the saved inbound UAS handle.
- Upstream received statuses `[100, 486]`; the final response retained the inbound Call-ID and `CSeq: 1 INVITE`.
- DUM event-loop TID and Python callback TID were both `113523`.
- Timings: DUM startup `3.419 ms`; callback/`decide()` `0.152 ms`; start to upstream 486 `61.172 ms`. These are one local smoke-run observation, not performance evidence.
- Final integration marker: `INTEGRATION_PASS`.

## Call Flow

1. The Python harness sends an SDP-free UDP INVITE to DUM on port 43761.
2. DUM emits 100 Trying and invokes `onNewSession(ServerInviteSessionHandle, OfferAnswerType, SipMessage)` on its event-loop thread.
3. The extension acquires the GIL and calls Python with the inbound Call-ID, calling number, and called number. Python constructs `DecisionRequest`, calls the repository's `as_platform.decision.decide` with one `Action.FORWARD` rule, and returns the decision target URI.
4. Still on the DUM event-loop thread, C++ calls `makeInviteSession`, reads its returned `shared_ptr<SipMessage>` and generated Call-ID, saves the inbound UAS handle under that outbound Call-ID, and sends the message with `DialogUsageManager::send`.
5. The local peer records the outbound INVITE and replies with a final 486 matching its transaction headers. DUM emits the UAC non-2xx ACK and invokes the real UAC failure callback.
6. `onFailure` looks up the generated outbound Call-ID and calls `reject(486)` on only the associated inbound UAS handle. The upstream client receives 486 under the original inbound Call-ID and sends its non-2xx ACK.

## Commands And Exit Codes

The final gate was run as:

```sh
SPIKE_UAS_PORT=43761 SPIKE_UPSTREAM_PORT=43762 SPIKE_DOWNSTREAM_PORT=43763 \
  bash /tmp/as-resip-dum-two-leg-spike/run.sh
```

Overall exit code: `0` (`logs/run.log`). The runner recorded:

| Command/check | Exit |
| --- | ---: |
| Three-port loopback preflight using uv CPython 3.10.21 | 0 |
| `timeout 75s bash /tmp/as-resip-dum-two-leg-spike/build.sh` | 0 |
| Native compile/link inside `build.sh` (`timeout 60s`, C++17, exact CPython 3.10 headers/library and reSIProcate 1.14.0 build) | 0 |
| `timeout 10s ldd /tmp/as-resip-dum-two-leg-spike/_resip_dum.cpython-310-x86_64-linux-gnu.so` | 0 |
| Exact `ldd` path checks for libpython, libdum, libresip, librutil, and libresipares | 0 |
| `timeout 45s env PYTHONDONTWRITEBYTECODE=1 /home/shudong/project/3rdparty-as/.venv/bin/python /tmp/as-resip-dum-two-leg-spike/run_integration.py` | 0 |
| `git -C /home/shudong/project/3rdparty-as -c core.quotePath=false status --short` | 0 |
| `diff -u /tmp/as-resip-dum-two-leg-spike/repo-status-baseline.txt /tmp/as-resip-dum-two-leg-spike/logs/repo-status-current.txt` | 0; empty diff |
| `/usr/bin/c++ --version` | 0 |

The final build's native command (exit `0`) was:

```sh
timeout 60s env TMPDIR=/tmp/as-resip-dum-two-leg-spike/tmp /usr/bin/c++ \
  -std=c++17 -O2 -g -Wall -Wextra -fPIC -shared -pthread \
  -I/home/shudong/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/include/python3.10 \
  -I/tmp/as-resiprocate-userbuild/upstream-minimal-20260930 \
  -I/tmp/as-resiprocate-userbuild/resiprocate-1.14.0 \
  -I/tmp/as-resiprocate-userbuild/resiprocate-1.14.0/rutil/dns/ares \
  /tmp/as-resip-dum-two-leg-spike/dum_two_leg_module.cxx \
  -L/tmp/as-resiprocate-userbuild/upstream-minimal-20260930/resip/dum \
  -L/tmp/as-resiprocate-userbuild/upstream-minimal-20260930/resip/stack \
  -L/tmp/as-resiprocate-userbuild/upstream-minimal-20260930/rutil \
  -L/tmp/as-resiprocate-userbuild/upstream-minimal-20260930/rutil/dns/ares \
  -L/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib \
  -Wl,-rpath,/tmp/as-resiprocate-userbuild/upstream-minimal-20260930/resip/dum:/tmp/as-resiprocate-userbuild/upstream-minimal-20260930/resip/stack:/tmp/as-resiprocate-userbuild/upstream-minimal-20260930/rutil:/tmp/as-resiprocate-userbuild/upstream-minimal-20260930/rutil/dns/ares:/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib \
  -ldum -lresip -lrutil -lssl -lcrypto -ldl \
  -Wl,--no-as-needed -lpython3.10 -Wl,--as-needed \
  -o /tmp/as-resip-dum-two-leg-spike/_resip_dum.cpython-310-x86_64-linux-gnu.so
```

No sudo, apt, system package installation, repository edit, delete, commit, push, or branch operation was performed. The repository's pre-existing modified/untracked status was identical before and after the run.

## Artifacts

- Native source and extension: `dum_two_leg_module.cxx`, `_resip_dum.cpython-310-x86_64-linux-gnu.so`.
- Python harness and runners: `run_integration.py`, `build.sh`, `run.sh`.
- SIP wire captures: `wire/upstream-inbound-invite.sip`, `wire/downstream-outbound-invite.sip`, `wire/downstream-486-busy-here.sip`, `wire/downstream-followup-00.sip` (DUM ACK), `wire/upstream-response-00.sip` (100), `wire/upstream-response-01.sip` (486), and `wire/upstream-client-ack.sip`.
- Logs and checks: `logs/run.log`, `logs/native-build.log`, `logs/ldd.log`, `logs/dependency-check.log`, `logs/integration.log`, `logs/explicit-port-check.log`, `logs/compiler-version.log`, `logs/repo-status-current.txt`, `logs/repo-status-diff.log`, `logs/repo-status-final-diff.log`, and `repo-status-baseline.txt`.

## Limitations

- This exercises only an exploratory route decision and one downstream 486 failure path. It is not an approved product API, SIP adapter, or complete B2BUA implementation.
- The request and outbound INVITE contain no SDP. No arbitrary headers or SDP are forwarded. This does not prove REQ-F-4, SDP byte identity, or media behavior.
- The smoke does not establish full B2BUA semantics, E1 S1-S11, D10 recovery, D11 SDP byte identity, E4/E5, or release K2.
- It does not test CANCEL, forked dialogs, retransmission loss/races, additional status mappings, in-dialog requests, overload, shutdown with active calls, or concurrent calls.
- It shows one event-loop/callback affinity path in this build; it is not a general thread-safety certification for reSIProcate handles or other DUM APIs.
- The UAS-port preflight is a bind-check followed by release before DUM binds that explicit port, so another process could theoretically race for it.
- The upstream ACK is sent and saved by the test client, but the harness does not assert UAS transaction termination after that ACK.
- Measured timings are a single loopback smoke run and are not latency, throughput, CPS, or capacity claims.