# D9 Primitive Bridge Spike

Date: 2026-09-30

## Outcome

The minimal CPython extension passed the same-thread and one-native-thread callback checks. Both paths returned ordered results, propagated the original callback exception with its traceback, and balanced callback/result references across successful and failing batches. For a 257-event worker batch, callbacks observed one native thread ID, distinct from the calling thread.

This supports only the feasibility of an in-process CPython/native callback bridge. It does not establish a usable reSIProcate DUM binding or any DUM handle thread-affinity rule.

## Runtime and Build

The harness ran through `uv run --no-sync --project /home/shudong/project/3rdparty-as python` and reported:

- CPython 3.10.21, executable `/home/shudong/project/3rdparty-as/.venv/bin/python3` (real path `/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/bin/python3.10`)
- `sysconfig.get_path("include")`: `/home/shudong/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/include/python3.10` (the include directory used by the compiler)
- `sysconfig.get_config_var("INCLUDEPY")`: `/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/include/python3.10`
- Library directory `/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib`, library `libpython3.10.so`
- ABI `cpython-310-x86_64-linux-gnu`; extension suffix `.cpython-310-x86_64-linux-gnu.so`
- Compiler `/usr/bin/c++`: GCC 9.4.0 (`c++ (Ubuntu 9.4.0-1ubuntu1~20.04.2) 9.4.0`)

Exact build command (run from the repository, with a 60-second timeout):

```sh
timeout 60s env TMPDIR=/tmp/as-resip-python-bridge-spike/tmp \
  /usr/bin/c++ -std=c++17 -O2 -Wall -Wextra -fPIC -shared -pthread \
  -I/home/shudong/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/include/python3.10 \
  /tmp/as-resip-python-bridge-spike/bridge.cpp \
  -L/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib \
  -Wl,-rpath,/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib \
  -lpython3.10 \
  -o /tmp/as-resip-python-bridge-spike/as_resip_bridge.cpython-310-x86_64-linux-gnu.so
```

The harness command used a 60-second timeout and the same uv project interpreter:

```sh
timeout 60s env PYTHONDONTWRITEBYTECODE=1 \
  UV_CACHE_DIR=/tmp/as-resip-python-bridge-spike/uv-cache \
  UV_NO_PROGRESS=1 UV_PYTHON_DOWNLOADS=never \
  uv run --no-sync --project /home/shudong/project/3rdparty-as python \
  /tmp/as-resip-python-bridge-spike/harness.py \
  /tmp/as-resip-python-bridge-spike/as_resip_bridge.cpython-310-x86_64-linux-gnu.so
```

Final exit codes: compiler version 0, build 0, `ldd` linkage check 0, harness 0, runner 0. `ldd` resolved `libpython3.10.so.1.0` from the specified uv library directory. No sudo, apt, or system package installation was used.

The first harness attempt exited 1 after a harness-only assertion incorrectly required `get_path("include")` and `INCLUDEPY` to be the same string. Runtime output showed the two distinct uv paths above. The assertion was corrected to check each reported value independently; the extension had already built and linked successfully, and the final full harness passed.

## Checks and Timings

The order/result check used 257 tokens (`0..256`) and a deterministic callback returning `token * 3 + 7`. The worker callback reported one stable native ID for the whole batch, different from the caller. Exception tests raised at token 7 and checked exception object identity and traceback on both paths. Reference checks covered callback references after 50 batches and result-object references after 25 successful and 25 partial-result-exception batches per path.

Timings are medians of seven measured runner calls after one warm-up call per size/path. The timed region is the runner call; the worker measurement includes creating/joining its one native thread and acquiring/releasing the GIL per callback. Expected-value generation and result assertions are outside the timed region.

| Callbacks | Same-thread median | Same-thread per callback | One-native-thread median | Worker per callback |
|---:|---:|---:|---:|---:|
| 1 | 500 ns | 0.500 us | 184,000 ns | 184.000 us |
| 100 | 21,800 ns | 0.218 us | 200,601 ns | 2.006 us |
| 1,000 | 204,400 ns | 0.204 us | 351,200 ns | 0.351 us |
| 10,000 | 1,237,101 ns | 0.124 us | 3,042,603 ns | 0.304 us |

The callable was a cheap pure-Python integer transform, `(token * 17 + 5) & 0xFFFFFFFF`. These microbenchmarks measure only this local bridge and interpreter; they are not production latency, throughput, or CPS measurements.

## Boundaries

The worker implementation creates one `std::thread` per batch, releases the caller's GIL while joining, and uses `PyGILState_Ensure/Release` around each worker callback. It owns callback/result references explicitly and captures/restores worker exceptions with `PyErr_Fetch/PyErr_Restore`.

The experiment used one CPython 3.10.21 main interpreter, synchronous batches, and one worker at a time. It does not test subinterpreters, interpreter shutdown races, concurrent batches, callback cancellation, or callbacks that wait on other Python threads. It does not establish that any reSIProcate DUM object may be accessed from the worker thread.

It does not prove a usable reSIProcate DUM binding, correct handle thread affinity, production latency/CPS, a DUM+Python adapter, D10 state recovery, D11 SDP wire identity, E1/E4/E5, or K2 release.

## Artifacts and Repository Check

All source, extension, build temporaries, uv cache, logs, and reports are under `/tmp/as-resip-python-bridge-spike`. Key files are `bridge.cpp`, `harness.py`, `run.sh`, `as_resip_bridge.cpython-310-x86_64-linux-gnu.so`, `run.log`, `build.log`, `harness.log`, `extension-linkage.log`, and `compiler-version.log`.

`git status --short` was saved before and after the spike; the comparison is empty (exit code 0). The pre-existing modified/untracked repository files are unchanged, and no repository files were created or edited by this experiment.