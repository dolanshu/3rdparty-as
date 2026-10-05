"""Load the M7 minimal product-path two-leg native extension."""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

_DEFAULT_BUILD_DIR = Path(__file__).resolve().parents[3] / "native" / "resip_two_leg" / "build"


def _extension_build_dir() -> Path:
    override = os.environ.get("AS_RESIP_TWO_LEG_BUILD")
    if override:
        return Path(override)
    return _DEFAULT_BUILD_DIR


def load_resip_two_leg_extension() -> ModuleType | None:
    """Import ``_resip_two_leg`` when the cmake module is on disk."""
    build_dir = _extension_build_dir()
    suffixes = importlib.machinery.EXTENSION_SUFFIXES
    candidates = [build_dir / f"_resip_two_leg{suffix}" for suffix in suffixes]
    candidates.append(build_dir / "_resip_two_leg.so")
    module_path = next((path for path in candidates if path.is_file()), None)
    if module_path is None:
        return None

    module_name = "_resip_two_leg"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
