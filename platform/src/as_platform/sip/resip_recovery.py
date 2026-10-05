"""Product-path RecoveryTU session (native ``_resip_recovery`` + checkpoint adapter)."""

from __future__ import annotations

import importlib
import importlib.machinery
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

from as_platform.state.call_checkpoint import CallStateCheckpoint

_DEFAULT_BUILD_DIR = Path(__file__).resolve().parents[3] / "native" / "resip_recovery" / "build"
_ADAPTER_FORMAT = "d10-native-checkpoint-v1"


def _extension_build_dir() -> Path:
    override = os.environ.get("AS_RESIP_RECOVERY_BUILD")
    if override:
        return Path(override)
    return _DEFAULT_BUILD_DIR


def load_resip_recovery_extension() -> ModuleType | None:
    """Import ``_resip_recovery`` when the cmake module is on disk."""
    build_dir = _extension_build_dir()
    suffixes = importlib.machinery.EXTENSION_SUFFIXES
    candidates = [build_dir / f"_resip_recovery{suffix}" for suffix in suffixes]
    candidates.append(build_dir / "_resip_recovery.so")
    module_path = next((path for path in candidates if path.is_file()), None)
    if module_path is None:
        return None

    build_str = str(build_dir)
    if build_str not in sys.path:
        sys.path.insert(0, build_str)

    return importlib.import_module("_resip_recovery")


def fields_from_checkpoint(checkpoint: CallStateCheckpoint) -> dict[str, str]:
    """Serialize a checkpoint to the native adapter field mapping (testbed-compatible)."""
    fields = {"format": _ADAPTER_FORMAT}
    for prefix, leg in (("uas", checkpoint.uas_leg), ("uac", checkpoint.uac_leg)):
        fields.update(
            {
                f"{prefix}_call_id": leg.call_id,
                f"{prefix}_local_tag": leg.local_tag,
                f"{prefix}_remote_tag": leg.remote_tag,
                f"{prefix}_local_uri": leg.local_uri,
                f"{prefix}_remote_uri": leg.remote_uri,
                f"{prefix}_remote_target": leg.remote_target,
                f"{prefix}_local_cseq": str(leg.local_cseq),
                f"{prefix}_remote_cseq": str(leg.remote_cseq),
                f"{prefix}_route_count": str(len(leg.route_set)),
            }
        )
        fields.update(
            {f"{prefix}_route_{index}": route for index, route in enumerate(leg.route_set)}
        )
    return fields


def write_native_adapter(path: Path, checkpoint: CallStateCheckpoint) -> None:
    """Write checkpoint fields consumed by the native RecoveryTU loader."""
    fields = fields_from_checkpoint(checkpoint)
    path.write_text(
        "".join(f"{name}={value}\n" for name, value in fields.items()),
        encoding="utf-8",
    )


class RecoveryStackSession:
    """Start/stop a minimal product RecoveryTU stack from a typed checkpoint."""

    def __init__(self, extension: ModuleType | None = None) -> None:
        """Optionally inject a pre-loaded ``_resip_recovery`` module (tests)."""
        self._extension = extension
        self._handle: Any = None
        self._adapter_path: Path | None = None
        self._owns_adapter_file = False

    @property
    def listen_port(self) -> int:
        """UDP port bound by the native recovery stack after :meth:`start`."""
        if self._handle is None:
            raise RuntimeError("RecoveryStackSession is not started")
        if self._extension is None:
            raise RuntimeError("RecoveryStackSession extension is missing")
        return int(self._extension.get_listen_port(self._handle))

    def start(self, checkpoint: CallStateCheckpoint, listen_port: int = 0) -> None:
        """Register RecoveryTU on a fresh SipStack+DUM and load ``checkpoint``."""
        if self._handle is not None:
            raise RuntimeError("RecoveryStackSession is already started")
        extension = self._extension or load_resip_recovery_extension()
        if extension is None:
            raise RuntimeError(
                "platform _resip_recovery extension not built; run make m7-platform-recovery-build"
            )
        self._extension = extension

        adapter_dir = Path(tempfile.mkdtemp(prefix="as-recovery-adapter-"))
        adapter_path = adapter_dir / "checkpoint.fields"
        write_native_adapter(adapter_path, checkpoint)
        self._adapter_path = adapter_path
        self._owns_adapter_file = True

        self._handle = extension.start(str(adapter_path), int(listen_port))

    def start_from_adapter_file(self, adapter_path: Path | str, listen_port: int = 0) -> None:
        """Load RecoveryTU from an on-disk adapter file (test / harness only)."""
        if self._handle is not None:
            raise RuntimeError("RecoveryStackSession is already started")
        extension = self._extension or load_resip_recovery_extension()
        if extension is None:
            raise RuntimeError(
                "platform _resip_recovery extension not built; run make m7-platform-recovery-build"
            )
        self._extension = extension
        path = Path(adapter_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        self._adapter_path = None
        self._owns_adapter_file = False
        self._handle = extension.start(str(path), int(listen_port))

    def process(self, timeout_ms: int = 50) -> None:
        """Pump the native event loop (call from tests between UDP sends)."""
        if self._handle is None or self._extension is None:
            raise RuntimeError("RecoveryStackSession is not started")
        self._extension.process(self._handle, int(timeout_ms))

    def drain(self) -> None:
        """Drain the RecoveryTU fifo once."""
        if self._handle is None or self._extension is None:
            raise RuntimeError("RecoveryStackSession is not started")
        self._extension.drain(self._handle)

    def send_upstream_200(self) -> None:
        """Answer the matched upstream BYE after downstream 200."""
        if self._handle is None or self._extension is None:
            raise RuntimeError("RecoveryStackSession is not started")
        self._extension.send_upstream_200(self._handle)

    def status(self) -> dict[str, bool]:
        """Return native recovery progress flags for tests."""
        if self._handle is None or self._extension is None:
            raise RuntimeError("RecoveryStackSession is not started")
        return {
            "downstream_200": bool(self._extension.get_downstream_200(self._handle)),
            "upstream_200_queued": bool(self._extension.get_upstream_200_queued(self._handle)),
        }

    def stop(self) -> None:
        """Stop the native worker and remove the temporary adapter file."""
        if self._handle is None or self._extension is None:
            return
        self._extension.stop(self._handle)
        self._handle = None
        if self._adapter_path is not None and self._owns_adapter_file:
            try:
                self._adapter_path.unlink(missing_ok=True)
                self._adapter_path.parent.rmdir()
            except OSError:
                pass
            self._adapter_path = None
            self._owns_adapter_file = False
