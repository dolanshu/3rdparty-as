"""Guard: the kernel must not depend on anything that uses it.

`platform/` is the kernel. If it ever imports an application, a service or the
testbed, the layering is gone: the "one shared shell, N use cases" model
collapses, and inside a monorepo nothing else would catch it, because every
import resolves.

This guard is carried over from the POC library repository with a wider scope:
the POC only had to keep the library clear of two applications, this repository
also has `services/` and `testbed/`.

See AGENT.md §Layering and ADR-0001.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
KERNEL_SOURCE = REPOSITORY_ROOT / "platform" / "src" / "as_platform"

# What the kernel may never import: the import root of every non-kernel member.
# It is cross-checked against the workspace member list below, so adding a member
# without extending this list fails the gate.
FORBIDDEN_ROOTS: frozenset[str] = frozenset(
    {
        "as_translation",
        "as_anti_fraud",
        "as_config_service",
        "as_console",
        "as_simulators",
        "as_load",
    }
)


def _load_toml(path: Path) -> dict[str, Any]:
    """Read a TOML manifest on both 3.10 (tomli) and 3.11+ (tomllib)."""
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    return tomllib.loads(path.read_text(encoding="utf-8"))


def _kernel_modules() -> list[Path]:
    if not KERNEL_SOURCE.is_dir():
        return []
    return sorted(path for path in KERNEL_SOURCE.rglob("*.py") if "__pycache__" not in path.parts)


def _imported_roots(tree: ast.AST) -> set[str]:
    """Return the top-level package of every absolute import in one module."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_kernel_source_exists() -> None:
    """A moved kernel must fail this guard loudly, not make it pass vacuously."""
    assert KERNEL_SOURCE.is_dir(), f"kernel source not found at {KERNEL_SOURCE}"


@pytest.mark.parametrize("module_path", _kernel_modules(), ids=lambda path: path.name)
def test_kernel_does_not_import_a_consumer(module_path: Path) -> None:
    """A kernel module must not import an application, a service or the testbed."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    offenders = sorted(_imported_roots(tree) & FORBIDDEN_ROOTS)
    assert not offenders, f"{module_path.name} imports {offenders}"


def test_forbidden_roots_cover_every_other_member() -> None:
    """Every non-kernel workspace member must appear on the forbidden list."""
    manifest = _load_toml(REPOSITORY_ROOT / "pyproject.toml")
    members: list[str] = manifest["tool"]["uv"]["workspace"]["members"]

    for member in members:
        if member == "platform":
            continue
        member_manifest = _load_toml(REPOSITORY_ROOT / member / "pyproject.toml")
        packages: list[str] = member_manifest["tool"]["hatch"]["build"]["targets"]["wheel"][
            "packages"
        ]
        import_root = Path(packages[0]).name
        assert import_root in FORBIDDEN_ROOTS, (
            f"{member} is a workspace member but {import_root} is not guarded; "
            "add it to FORBIDDEN_ROOTS"
        )
