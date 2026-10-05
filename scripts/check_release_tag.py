"""Reject tags that do not match the application's single version source."""

import os
from pathlib import Path
import re
from runpy import run_path


def check_tag(tag: str, version: str) -> None:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) or tag != f"v{version}":
        raise ValueError(f"Release tag must be v{version}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    version = run_path(str(root / "src" / "mac_converter" / "__init__.py"))["__version__"]
    try:
        check_tag(os.environ.get("RELEASE_TAG", ""), version)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print(f"Tag matches application version: v{version}")


if __name__ == "__main__":
    main()
