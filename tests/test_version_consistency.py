"""Guard: the product version has one home and the changelog agrees with it.

The POC shipped with `VERSION` at 0.2.0 and `pyproject.toml` at 0.1.0 in the
same repository. Two homes for one number is a defect that only shows up at
delivery time, so it is guarded here instead.

Separation of concerns, and why it is not drift (ADR-0018):

* `./VERSION` — the **product** release version. One number per delivery, because
  what the operator receives is one system, not seven packages.
* `<member>/pyproject.toml` — that **component's** interface version, moved
  independently when its internal interface changes.

Two different things, therefore two files — and no member may own a VERSION file.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPOSITORY_ROOT / "VERSION"
CHANGELOG = REPOSITORY_ROOT / "CHANGELOG.md"

# SemVer core, optional pre-release / build metadata. Deliberately stricter than
# PEP 440: a delivery version must be readable by an operator, not just by pip.
SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


def _load_toml(path: Path) -> dict[str, Any]:
    """Read a TOML manifest on both 3.10 (tomli) and 3.11+ (tomllib)."""
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    return tomllib.loads(path.read_text(encoding="utf-8"))


def _members() -> list[str]:
    return list(
        _load_toml(REPOSITORY_ROOT / "pyproject.toml")["tool"]["uv"]["workspace"]["members"]
    )


def test_version_file_is_present_and_well_formed() -> None:
    """The product version exists and is a readable SemVer."""
    assert VERSION_FILE.is_file(), "VERSION is missing"
    raw = VERSION_FILE.read_text(encoding="utf-8").strip()
    assert SEMVER.match(raw), f"VERSION is not a SemVer: {raw!r}"


def test_changelog_head_agrees_with_the_version_file() -> None:
    """The newest changelog release heading is the version we are shipping."""
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    headings = re.findall(r"^## \[([^\]]+)\]", CHANGELOG.read_text(encoding="utf-8"), re.MULTILINE)
    assert headings, "CHANGELOG.md has no version heading"
    assert headings[0] == version, (
        f"CHANGELOG.md starts at {headings[0]}, VERSION says {version}; bump both together"
    )


@pytest.mark.parametrize("member", _members())
def test_component_version_is_well_formed(member: str) -> None:
    """A component version is its own number, but it must still be a SemVer."""
    manifest = _load_toml(REPOSITORY_ROOT / member / "pyproject.toml")
    version = manifest["project"]["version"]
    assert SEMVER.match(version), f"{member} version is not a SemVer: {version!r}"
