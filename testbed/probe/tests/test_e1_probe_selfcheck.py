"""Self-check of the E1 probe harness: it must be able to run, and to fail.

ADR-0019 consequence K2 keeps the SIP adapter in ``platform/`` closed until the
E1 probe has replayed the M1 baseline on a real socket. That makes the harness
itself load-bearing, and it can be wrong in two ways that are worse than being
wrong about the stack: it can fail to run at all, which reads as "not yet" and
closes nothing; or it can pass without comparing anything, which would release
K2 on nothing. These tests close both doors, and they do it the way the probe
is really run --- over a loopback socket, against a peer that answers.

The peer is ``fake_stack``: a bindings stand-in that opens the probe's bindings
gate, plus a replay server that answers every message the probe delivers with
the next ``out-*`` message of the baseline. That peer is a script, not a SIP
stack, so what these tests establish is about the harness:

1. a run whose emissions match the baseline exits 0 and reports ``PASS``;
2. a run with one tampered expectation exits 1 and names the difference;
3. a run without importable bindings exits 2, loudly, before anything else.

They do **not** establish that reSIProcate reproduces the baseline. Only the
real bindings on a real host can do that, and that run belongs in
``docs/acceptance/report.md``.

Marker: ``integration`` --- these bind sockets on 127.0.0.1.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

# Neither the probe package nor the scaffolding next to this file is installed,
# so put both parents on the path the way the other probe tests do.
_SELFCHECK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELFCHECK_DIR))
sys.path.insert(0, str(_SELFCHECK_DIR.parents[1]))

import fake_stack  # noqa: E402
from probe import e1_baseline_probe  # noqa: E402

pytestmark = pytest.mark.integration

#: The scenario whose first expected response the tamper test rewrites.
TAMPERED_SCENARIO_DIR: str = "S1-basic-call"
TAMPERED_MESSAGE: str = "02-out-100-trunk.txt"
TAMPERED_WAS: bytes = b"SIP/2.0 100 Trying"
TAMPERED_NOW: bytes = b"SIP/2.0 404 Not Found"


def _replay_script(root: Path, scenarios: Sequence[str]) -> tuple[bytes, ...]:
    """Collect the ``out-*`` messages the replay server has to answer with.

    Args:
        root: The baseline root the probe is pointed at.
        scenarios: The scenarios the probe will run, in the order it runs them.

    Returns:
        Every scenario's expected emissions, concatenated in that order: the
        probe drives all of its scenarios over one connection, so the peer
        answers with one continuous script.
    """
    script: list[bytes] = []
    for scenario in scenarios:
        directories = sorted(path for path in root.glob(f"{scenario}-*") if path.is_dir())
        assert directories, f"no baseline directory for {scenario} under {root}"
        script.extend(fake_stack.outbound_messages(directories[0]))
    return tuple(script)


def _run_probe(
    capsys: pytest.CaptureFixture[str],
    *,
    port: int,
    out_dir: Path,
    bindings_module: str,
    baseline_root: Path | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> tuple[int, str]:
    """Run the E1 probe in-process and capture its verdict.

    Args:
        capsys: The pytest fixture that captures what the probe prints.
        port: The port of the AS under probe.
        out_dir: Where the probe writes its evidence; a temporary directory.
        bindings_module: What to pass as ``--bindings-module``.
        baseline_root: When given, the baseline root to point the probe at
            instead of the one in the repository.
        monkeypatch: Needed only when ``baseline_root`` is given.

    Returns:
        The exit code, and everything the probe printed. The bindings gate
        exits the process rather than returning, so a ``SystemExit`` is folded
        into the code the same way a shell would see it.
    """
    if baseline_root is not None:
        assert monkeypatch is not None
        monkeypatch.setattr(e1_baseline_probe, "BASELINE_ROOT", baseline_root)
    argv = [
        "--host",
        fake_stack.DEFAULT_HOST,
        "--port",
        str(port),
        "--bindings-module",
        bindings_module,
        "--out-dir",
        str(out_dir),
    ]
    try:
        code = e1_baseline_probe.main(argv)
    except SystemExit as exit_request:
        code = exit_request.code if isinstance(exit_request.code, int) else -1
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_probe_passes_when_the_baseline_matches(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The harness replays S1-S4, compares them and exits 0 on a match."""
    scenarios = list(e1_baseline_probe.DEFAULT_SCENARIOS)
    server = fake_stack.ReplayServer(_replay_script(e1_baseline_probe.BASELINE_ROOT, scenarios))
    try:
        fake_stack.install_fake_bindings(monkeypatch)
        code, output = _run_probe(
            capsys,
            port=server.port,
            out_dir=tmp_path / "evidence",
            bindings_module=fake_stack.DEFAULT_BINDINGS_MODULE,
        )
    finally:
        server.close()

    assert code == e1_baseline_probe.EXIT_OK, output
    assert "no scenario was verified" not in output
    for scenario in scenarios:
        assert f"{scenario}: {e1_baseline_probe.PASS}" in output
    # The probe drove the peer over a real socket: every expected message was
    # asked for and answered.
    assert server.served == len(_replay_script(e1_baseline_probe.BASELINE_ROOT, scenarios))
    # Evidence was written, so the verdict can be re-derived from disk.
    assert (tmp_path / "evidence" / "S1-basic-call" / "01-actual.bin").is_file()


def test_probe_fails_and_names_the_difference_when_an_expectation_is_tampered(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """One rewritten expectation must turn into exit code 1 and a difference."""
    baseline_root = tmp_path / "baseline"
    shutil.copytree(e1_baseline_probe.BASELINE_ROOT, baseline_root)

    tampered = baseline_root / TAMPERED_SCENARIO_DIR / TAMPERED_MESSAGE
    original = tampered.read_bytes()
    assert TAMPERED_WAS in original, f"{tampered} no longer carries {TAMPERED_WAS!r}"
    tampered.write_bytes(original.replace(TAMPERED_WAS, TAMPERED_NOW))

    # The peer keeps replaying the untampered baseline: what differs is the
    # expectation, so the harness has to notice it.
    server = fake_stack.ReplayServer(
        _replay_script(e1_baseline_probe.BASELINE_ROOT, list(e1_baseline_probe.DEFAULT_SCENARIOS))
    )
    try:
        fake_stack.install_fake_bindings(monkeypatch)
        code, output = _run_probe(
            capsys,
            port=server.port,
            out_dir=tmp_path / "evidence",
            bindings_module=fake_stack.DEFAULT_BINDINGS_MODULE,
            baseline_root=baseline_root,
            monkeypatch=monkeypatch,
        )
    finally:
        server.close()

    assert code == e1_baseline_probe.EXIT_FAILED, output
    assert f"S1: {e1_baseline_probe.FAIL}" in output
    # A difference a reader cannot act on is no better than no difference: the
    # message number, the field and both values have to be in the report.
    assert "message 1: method/status differs" in output
    assert "actual '100'" in output
    assert "expected '404'" in output


def test_probe_exits_two_when_the_bindings_are_missing(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """A missing binding must stop the run with exit code 2, before anything."""
    server = fake_stack.ReplayServer(
        _replay_script(e1_baseline_probe.BASELINE_ROOT, list(e1_baseline_probe.DEFAULT_SCENARIOS))
    )
    try:
        # The probe stops at the bindings gate, so the peer stays idle; it is
        # closed all the same, so nothing leaks if that ever changes.
        code, output = _run_probe(
            capsys,
            port=server.port,
            out_dir=tmp_path / "evidence",
            bindings_module="as_probe_selfcheck_absent_bindings",
        )
    finally:
        server.close()

    assert code == e1_baseline_probe.EXIT_BINDINGS_MISSING, output
    assert "are not importable" in output
    # Nothing was compared, so no scenario may look verified.
    assert server.served == 0
    assert not (tmp_path / "evidence").exists()
