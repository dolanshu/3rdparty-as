"""Fail-closed scan for ADR annotations on architectural names.

REQ-G-3 requires non-obvious code to point at its ADR; ADR-0015 places this
scan outside ``make gate`` and runs it as an extra CI step (``make
gate-strict``). This script is that scan: it exits 1 with a ``file:line``
list on violation and 0 when clean.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# See ADR-0015: the markers mirror the component vocabulary of the
# architecture document (guards, stores, transports, policies, ...). Matching
# is a case-insensitive substring so a component cannot dodge the scan by
# renaming (``DownscaleGuardConfig`` still matches ``guard``).
MARKER_SUBSTRINGS: tuple[str, ...] = (
    "guard",
    "store",
    "transport",
    "policy",
    "controller",
    "session",
    "metrics",
    "telemetry",
    "drain",
    "scale",
)

_DEFINITION_PATTERN = re.compile(r"^\s*(?P<kind>class|def)\s+(?P<name>[A-Za-z_]\w*)")
_ADR_PATTERN = re.compile(r"ADR-\d+")

# See ADR-0015: the scan window is the 5 lines preceding the definition plus
# the definition line itself (a trailing ``# See ADR-00NN`` belongs to it).
# The same-file header is the leading lines holding the module docstring.
# Both live conventions count: ``# See ADR-00NN`` comments and ``(ADR-00NN)``
# doc references.
HEADER_LINE_COUNT = 15
PRECEDING_LINE_COUNT = 5

# See ADR-0015: leading-underscore definitions are module-private helpers,
# not architectural surface. Exempting them keeps false positives low while
# every public Guard/Store/... stays covered.
_PRIVATE_PREFIX = "_"

# See ADR-0015: grandfathered pre-M8 public names. Each entry is
# "<path-from-repo-root>:<name>". These are known REQ-G-3 gaps (bare stores,
# thin FastAPI dependency accessors, adapter helpers); annotate the file with
# its ADR the next time it is touched instead of growing this list.
GRANDFATHERED: frozenset[str] = frozenset(
    {
        # Thin wiring accessors in the management-plane API (ADR-0006).
        "services/config-service/src/as_config_service/api.py:require_auth_store",
        "services/config-service/src/as_config_service/api.py:require_distribution_store",
        "services/config-service/src/as_config_service/api.py:require_activation_stores",
        "services/config-service/src/as_config_service/api.py:require_as_instance_store",
        "services/config-service/src/as_config_service/api.py:get_session",
        # Row types and stores awaiting their ADR pointer (REQ-F-12/REQ-F-15).
        "services/config-service/src/as_config_service/as_instance_store.py:StoredAsInstance",
        "services/config-service/src/as_config_service/as_instance_store.py:AsInstanceStore",
        "services/config-service/src/as_config_service/as_instance_store.py:PostgresAsInstanceStore",
        "services/config-service/src/as_config_service/managed_rule_store.py:StoredManagedRule",
        "services/config-service/src/as_config_service/managed_rule_store.py:ManagedRuleStore",
        "services/config-service/src/as_config_service/managed_rule_store.py:PostgresManagedRuleStore",
        # SIP adapter helpers and recovery surface (ADR-0016, D10).
        "platform/src/as_platform/runtime/sip_stack_service.py:call_controller",
        "platform/src/as_platform/runtime/transport_env.py:load_transport_seam_from_env",
        "platform/src/as_platform/sip/recovery.py:ProcessStartRestoreResult",
        "platform/src/as_platform/sip/recovery.py:stop_native_recovery_sessions",
        "platform/src/as_platform/sip/recovery.py:on_process_start_restore",
        "platform/src/as_platform/sip/recovery_coordinator.py:ScheduledRestoreHandle",
        "platform/src/as_platform/sip/recovery_coordinator.py:schedule_restore",
        "platform/src/as_platform/sip/resip_recovery.py:RecoveryStackSession",
        "platform/src/as_platform/sip/resip_recovery.py:drain",
        "platform/src/as_platform/sip/resip_runtime.py:status_code_from_controller_effects",
        "platform/src/as_platform/sip/resip_runtime.py:controller_effects_for_inbound_invite",
        "platform/src/as_platform/sip/resip_runtime.py:call_controller",
    }
)


def _repo_root() -> Path:
    """Return the repository root derived from this script location."""
    return Path(__file__).resolve().parents[2]


def _scan_roots(root: Path) -> list[Path]:
    """Return the product source roots subject to REQ-G-3."""
    roots = [root / "platform" / "src"]
    for member in ("apps", "services"):
        base = root / member
        if base.is_dir():
            roots.extend(sorted(p for p in base.glob("*/src") if p.is_dir()))
    return roots


def _mentions_marker(name: str) -> bool:
    """Check whether a definition name carries an architectural marker."""
    lowered = name.lower()
    return any(marker in lowered for marker in MARKER_SUBSTRINGS)


def _definition_key(path: Path, root: Path, name: str) -> str:
    """Build the grandfather-allowlist key for one definition."""
    return f"{path.relative_to(root)}:{name}"


def _scan_file(path: Path, root: Path, used: set[str]) -> list[str]:
    """Scan one file; return ``path:line: kind name`` entries for violations."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header = "\n".join(lines[:HEADER_LINE_COUNT])
    header_ok = _ADR_PATTERN.search(header) is not None
    violations: list[str] = []
    for index, line in enumerate(lines):
        match = _DEFINITION_PATTERN.match(line)
        if match is None:
            continue
        name = match.group("name")
        if not _mentions_marker(name) or name.startswith(_PRIVATE_PREFIX):
            continue
        start = max(0, index - PRECEDING_LINE_COUNT)
        window = "\n".join(lines[start : index + 1])
        if _ADR_PATTERN.search(window) is not None or header_ok:
            continue
        key = _definition_key(path, root, name)
        if key in GRANDFATHERED:
            used.add(key)
            continue
        violations.append(f"{path.relative_to(root)}:{index + 1}: {match.group('kind')} {name}")
    return violations


def find_violations() -> tuple[list[str], list[str]]:
    """Scan all roots; return (violations, stale-allowlist-keys)."""
    root = _repo_root()
    violations: list[str] = []
    used: set[str] = set()
    checked = 0
    for scan_root in _scan_roots(root):
        for path in sorted(scan_root.rglob("*.py")):
            checked += 1
            violations.extend(_scan_file(path, root, used))
    stale = sorted(GRANDFATHERED - used)
    violations.sort()
    print(f"checked {checked} files", file=sys.stderr)
    return violations, stale


def main() -> int:
    """Run the scan; exit 1 with a file:line list on violation, 0 when clean."""
    violations, stale = find_violations()
    for key in stale:
        print(f"warning: allowlist entry no longer needed: {key}", file=sys.stderr)
    if violations:
        for violation in violations:
            print(f"{violation} lacks an ADR annotation (REQ-G-3)")
        return 1
    print("check_adr_annotations: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
