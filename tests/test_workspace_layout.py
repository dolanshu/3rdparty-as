"""Guard: the workspace declaration and the directory tree must agree.

The monorepo was created to kill three specific failures of the two-repository
POC: CI cloning a sibling checkout, a Dockerfile whose build context sat outside
the repository, and a version that drifted between two homes. All three are
structural, so all three are guarded by tests rather than by convention.

See AGENT.md §Layering and ADR-0001.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ROOT_MANIFEST = REPOSITORY_ROOT / "pyproject.toml"

# Tooling has exactly one home: the workspace root. A member that declares its
# own repeats the drift this repository was created to remove.
TOOL_TABLES_A_MEMBER_MUST_NOT_DECLARE = ("pytest", "ruff", "mypy")


def _load_toml(path: Path) -> dict[str, Any]:
    """Read a TOML manifest on both 3.10 (tomli) and 3.11+ (tomllib)."""
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    return tomllib.loads(path.read_text(encoding="utf-8"))


def _members() -> list[str]:
    manifest = _load_toml(ROOT_MANIFEST)
    return list(manifest["tool"]["uv"]["workspace"]["members"])


@pytest.fixture(scope="module")
def members() -> list[str]:
    """The declared workspace members."""
    return _members()


def test_root_manifest_is_virtual() -> None:
    """The root carries no [project]: it is a manifest, not a package."""
    manifest = _load_toml(ROOT_MANIFEST)
    assert "project" not in manifest, (
        "the workspace root must stay virtual; a [project] table here creates a "
        "third place for a version to live"
    )


def test_members_are_declared() -> None:
    """An empty member list would make every guard below pass vacuously."""
    assert _members(), "no workspace members declared"


@pytest.mark.parametrize("member", _members())
def test_member_directory_exists(member: str) -> None:
    """A declared member must exist on disk."""
    assert (REPOSITORY_ROOT / member).is_dir(), f"declared member {member} is missing"


@pytest.mark.parametrize("member", _members())
def test_member_declares_exactly_one_package(member: str) -> None:
    """One member, one importable package, under src/."""
    manifest = _load_toml(REPOSITORY_ROOT / member / "pyproject.toml")

    assert "name" in manifest.get("project", {}), f"{member} declares no [project].name"
    packages = manifest["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert len(packages) == 1, f"{member} must ship exactly one package, ships {packages}"

    package_dir = REPOSITORY_ROOT / member / packages[0]
    assert package_dir.is_dir(), f"{member} declares {packages[0]}, which does not exist"
    assert (package_dir / "__init__.py").is_file(), f"{package_dir} is not a package"
    assert packages[0].startswith("src/"), f"{member} must use the src/ layout, got {packages[0]}"
    assert Path(packages[0]).name.isidentifier(), f"{packages[0]} is not an importable name"


def test_distribution_names_are_unique(members: list[str]) -> None:
    """Two members under the same distribution name would silently shadow."""
    names = [
        _load_toml(REPOSITORY_ROOT / member / "pyproject.toml")["project"]["name"]
        for member in members
    ]
    assert len(names) == len(set(names)), f"duplicate distribution names: {sorted(names)}"


def test_ruff_knows_every_member_source_root(members: list[str]) -> None:
    """ruff's `src` list drives first-party import sorting; it must be complete."""
    root_manifest = _load_toml(ROOT_MANIFEST)
    declared_src = set(root_manifest["tool"]["ruff"]["src"])

    for member in members:
        manifest = _load_toml(REPOSITORY_ROOT / member / "pyproject.toml")
        package = manifest["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"][0]
        src_root = str((Path(member) / Path(package).parent).as_posix())
        assert src_root in declared_src, f"{member}: add {src_root} to [tool.ruff].src"


@pytest.mark.parametrize("member", _members())
def test_member_declares_no_tool_config_of_its_own(member: str) -> None:
    """Tooling lives at the root; a member config would silently diverge."""
    manifest = _load_toml(REPOSITORY_ROOT / member / "pyproject.toml")
    declared = sorted(
        tool for tool in TOOL_TABLES_A_MEMBER_MUST_NOT_DECLARE if tool in manifest.get("tool", {})
    )
    assert not declared, f"{member} must not declare [tool.{'] [tool.'.join(declared)}]"


@pytest.mark.parametrize("member", _members())
def test_member_carries_no_version_file(member: str) -> None:
    """A member VERSION file is the drift this repository was created to kill."""
    assert not (REPOSITORY_ROOT / member / "VERSION").exists(), (
        f"{member}/VERSION exists; a component's version has exactly one home, its pyproject"
    )
