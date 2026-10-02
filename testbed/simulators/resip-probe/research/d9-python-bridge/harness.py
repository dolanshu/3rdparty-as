import gc
import json
import platform
import statistics
import sys
import sysconfig
import threading
import time
from pathlib import Path


EXPECTED_PYTHON = Path(
    "/home/shudong/project/3rdparty-as/.venv/bin/python3"
).resolve()
EXPECTED_INCLUDE = (
    "/home/shudong/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu"
    "/include/python3.10"
)
EXPECTED_INCLUDE_CONFIG = (
    "/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu"
    "/include/python3.10"
)
EXPECTED_LIBDIR = (
    "/home/shudong/.local/share/uv/python/cpython-3.10.21-linux-x86_64-gnu/lib"
)
EXPECTED_LIBRARY = "libpython3.10.so"
EXPECTED_EXTENSION_SUFFIX = ".cpython-310-x86_64-linux-gnu.so"


def emit(record):
    print(json.dumps(record, sort_keys=True))


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: harness.py EXTENSION_PATH")

    runtime = {
        "event": "interpreter",
        "implementation": platform.python_implementation(),
        "version": sys.version,
        "executable": sys.executable,
        "executable_realpath": str(Path(sys.executable).resolve()),
        "include": sysconfig.get_path("include"),
        "include_config": sysconfig.get_config_var("INCLUDEPY"),
        "libdir": sysconfig.get_config_var("LIBDIR"),
        "library": sysconfig.get_config_var("LDLIBRARY"),
        "extension_suffix": sysconfig.get_config_var("EXT_SUFFIX"),
        "soabi": sysconfig.get_config_var("SOABI"),
    }
    emit(runtime)

    assert platform.python_implementation() == "CPython"
    assert sys.version_info[:3] == (3, 10, 21)
    assert Path(sys.executable).resolve() == EXPECTED_PYTHON
    assert sysconfig.get_path("include") == EXPECTED_INCLUDE
    assert sysconfig.get_config_var("INCLUDEPY") == EXPECTED_INCLUDE_CONFIG
    assert sysconfig.get_config_var("LIBDIR") == EXPECTED_LIBDIR
    assert sysconfig.get_config_var("LDLIBRARY") == EXPECTED_LIBRARY
    assert sysconfig.get_config_var("EXT_SUFFIX") == EXPECTED_EXTENSION_SUFFIX

    extension_path = Path(sys.argv[1]).resolve()
    assert extension_path.name.endswith(EXPECTED_EXTENSION_SUFFIX)
    sys.path.insert(0, str(extension_path.parent))
    import as_resip_bridge as bridge

    main_native_id = threading.get_native_id()
    event_count = 257
    expected_tokens = list(range(event_count))
    expected_results = [token * 3 + 7 for token in expected_tokens]

    same_thread_tokens = []
    same_thread_ids = set()

    def same_thread_callback(token):
        same_thread_tokens.append(token)
        same_thread_ids.add(threading.get_native_id())
        return token * 3 + 7

    same_thread_results = bridge.run_same(same_thread_callback, event_count)
    assert same_thread_tokens == expected_tokens
    assert same_thread_results == expected_results
    assert same_thread_ids == {main_native_id}

    worker_tokens = []
    worker_native_ids = set()

    def worker_callback(token):
        worker_tokens.append(token)
        worker_native_ids.add(threading.get_native_id())
        return token * 3 + 7

    worker_results = bridge.run_worker(worker_callback, event_count)
    assert worker_tokens == expected_tokens
    assert worker_results == expected_results
    assert len(worker_native_ids) == 1
    assert main_native_id not in worker_native_ids
    emit(
        {
            "event": "ordering_and_thread_identity",
            "callback_count": event_count,
            "same_thread_native_id": main_native_id,
            "worker_native_ids": sorted(worker_native_ids),
            "same_thread_order_and_results": "PASS",
            "worker_order_and_results": "PASS",
            "worker_uses_one_native_thread_for_batch": "PASS",
        }
    )

    class CallbackFailure(Exception):
        pass

    def verify_exception(runner, label):
        expected_exception = CallbackFailure(f"raised at event 7 via {label}")
        seen_tokens = []

        def raising_callback(token):
            seen_tokens.append(token)
            if token == 7:
                raise expected_exception
            return token

        try:
            runner(raising_callback, 20)
        except CallbackFailure as caught:
            assert caught is expected_exception
            assert str(caught) == f"raised at event 7 via {label}"
            assert caught.__traceback__ is not None
        else:
            raise AssertionError(f"{label} callback exception was not propagated")
        assert seen_tokens == list(range(8))

    verify_exception(bridge.run_same, "same-thread")
    verify_exception(bridge.run_worker, "worker")
    emit(
        {
            "event": "exception_propagation",
            "same_thread_exception_identity_and_traceback": "PASS",
            "worker_exception_identity_and_traceback": "PASS",
        }
    )

    def verify_callback_reference_count(runner, label):
        def callback(token):
            return token + 1

        before = sys.getrefcount(callback)
        for _ in range(50):
            assert runner(callback, 3) == [1, 2, 3]
        gc.collect()
        after = sys.getrefcount(callback)
        assert after == before, (label, before, after)

    verify_callback_reference_count(bridge.run_same, "same-thread")
    verify_callback_reference_count(bridge.run_worker, "worker")
    emit(
        {
            "event": "callback_reference_counts",
            "same_thread_after_50_batches": "PASS",
            "worker_after_50_batches": "PASS",
        }
    )

    def verify_result_reference_cleanup(runner, label):
        result_object = object()
        failure_message = f"partial result cleanup via {label}"

        def successful_callback(token):
            return result_object

        def failing_callback(token):
            if token == 3:
                raise CallbackFailure(failure_message)
            return result_object

        before = sys.getrefcount(result_object)
        for _ in range(25):
            results = runner(successful_callback, 5)
            assert all(result is result_object for result in results)
            del results
        for _ in range(25):
            try:
                runner(failing_callback, 6)
            except CallbackFailure as caught:
                assert str(caught) == failure_message
            else:
                raise AssertionError(f"{label} partial-result exception was lost")
        gc.collect()
        after = sys.getrefcount(result_object)
        assert after == before, (label, before, after)

    verify_result_reference_cleanup(bridge.run_same, "same-thread")
    verify_result_reference_cleanup(bridge.run_worker, "worker")
    emit(
        {
            "event": "result_reference_cleanup",
            "same_thread_success_and_exception_paths": "PASS",
            "worker_success_and_exception_paths": "PASS",
        }
    )

    def cheap_deterministic_callback(token):
        return (token * 17 + 5) & 0xFFFFFFFF

    repeat_count = 7
    for callback_count in (1, 100, 1000, 10000):
        expected = [
            cheap_deterministic_callback(token)
            for token in range(callback_count)
        ]
        for path_name, runner in (
            ("same_thread", bridge.run_same),
            ("one_native_thread", bridge.run_worker),
        ):
            runner(cheap_deterministic_callback, callback_count)
            samples_ns = []
            for _ in range(repeat_count):
                started_ns = time.perf_counter_ns()
                results = runner(cheap_deterministic_callback, callback_count)
                elapsed_ns = time.perf_counter_ns() - started_ns
                assert results == expected
                samples_ns.append(elapsed_ns)
            median_ns = int(statistics.median(samples_ns))
            emit(
                {
                    "event": "timing",
                    "path": path_name,
                    "callbacks": callback_count,
                    "repeats": repeat_count,
                    "samples_ns": samples_ns,
                    "median_ns": median_ns,
                    "median_us_per_callback": round(
                        median_ns / callback_count / 1000, 3
                    ),
                }
            )

    emit({"event": "result", "status": "PASS"})


if __name__ == "__main__":
    main()