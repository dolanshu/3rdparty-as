# D9 DUM-to-Python Slice

Status: **PASS** for this throwaway feasibility slice. This is not a product adapter, a full B2BUA, an acceptance result, or approval of the selected bridge design.

## Evidence

- Built `_resip_dum.cpython-310-x86_64-linux-gnu.so` against the repo venv's CPython 3.10.21 and the supplied reSIProcate 1.14.0 source/build.
- `ldd` resolved the uv-managed `libpython3.10.so.1.0`, `libdum-1.14.so`, `libresip-1.14.so`, `librutil-1.14.so`, and `libresipares-1.14.so` from the requested paths.
- Policy case: the UDP peer sent a complete INVITE to loopback port 53576 and received `SIP/2.0 404 Not Found`. The callback imported and called `as_platform.decision.decide` with a real `DecisionRequest` and empty `RuleSet`; the decision was `NOT_FOUND`.
- Policy thread markers: Python caller TID `109932`; DUM event-loop and callback TID `109935`. The response and callback markers were asserted by the harness.
- Exception case: the callback raised `RuntimeError("intentional callback failure")`; the bridge captured the error, did not crash, and the UDP peer received `SIP/2.0 500 Server Internal Error`. DUM event-loop and callback TID were `109939`, distinct from caller TID `109932`.
- Repository status exactly matched the pre-task snapshot; the baseline comparison returned exit 0.

## Commands And Exit Codes

| Command | Exit |
| --- | ---: |
| `sh /tmp/as-resip-dum-python-slice/build.sh` | 0 |
| `ldd /tmp/as-resip-dum-python-slice/build/_resip_dum.cpython-310-x86_64-linux-gnu.so` | 0 |
| `env PYTHONDONTWRITEBYTECODE=1 /home/shudong/project/3rdparty-as/.venv/bin/python /tmp/as-resip-dum-python-slice/run_integration.py` | 0 |
| `git -C /home/shudong/project/3rdparty-as -c core.quotePath=false status --short --untracked-files=all` | 0 |
| Baseline `diff` via `bash /tmp/as-resip-dum-python-slice/validate.sh` | 0 |
| `bash /tmp/as-resip-dum-python-slice/validate.sh` overall | 0 |

Two intermediate full-run attempts exited 1 only because the scratch baseline snapshot first had an incorrect untracked marker, then lacked a final newline. The DUM integration and native checks passed; after correcting the scratch comparison, the final run exited 0.

Full command output and statuses are in `logs/`: `build.log`, `ldd.log`, `dependency-check.log`, `integration.log`, `repo-status.log`, `baseline-compare.log`, `summary.log`, and `validate-trace.log`.

## Scope Limits

- No outbound UAC leg or cross-leg controller.
- No handle-affinity proof beyond keeping all DUM/SipStack/session handles on the event-loop thread and passing only scalar/string values to Python.
- No E1 baseline comparison or SDP byte-preservation check.
- No D10 recovery, E4 TLS, E1/E4/E5 closure, or K2 release.
- No full B2BUA, acceptance run, or product bridge decision. This materially adds D9 feasibility evidence only.