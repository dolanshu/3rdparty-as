"""Run the translation use case process shell with optional product SIP runtime."""

from __future__ import annotations

import os


def main() -> int:
    """Set ``AS_USE_CASE=translation`` and delegate to the platform process shell."""
    os.environ.setdefault("AS_USE_CASE", "translation")
    from as_platform.__main__ import main as platform_main

    return platform_main()


if __name__ == "__main__":
    raise SystemExit(main())
