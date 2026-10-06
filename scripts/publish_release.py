"""Publish only checked CI artifacts for the exact version and source commit."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from runpy import run_path
import subprocess


def checked_assets(directory: Path, expected_version: str, expected_commit: str) -> list[Path]:
    verification = json.loads((directory / "RELEASE_VERIFICATION.json").read_text(encoding="utf-8"))
    if verification["version"] != expected_version or verification["commit"] != expected_commit:
        raise ValueError("Artifact version or commit does not match the release source")
    if verification["smoke"]["passed"] is not True:
        raise ValueError("Artifact did not pass EXE verification")
    expected_names = {
        "MacAddressConverter.exe",
        f"NetworkTools-{expected_version}-windows-x64.zip",
        "RELEASE_VERIFICATION.json",
    }
    entries = {}
    for line in (directory / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name not in expected_names or name in entries:
            raise ValueError("Unexpected or duplicate checksum entry")
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Checksum mismatch: {name}")
        entries[name] = digest
    if set(entries) != expected_names:
        raise ValueError("Missing release asset checksum")
    if verification["smoke"]["sha256"] != entries["MacAddressConverter.exe"]:
        raise ValueError("Verified EXE hash does not match the release asset")
    return [directory / name for name in sorted(expected_names)] + [directory / "SHA256SUMS.txt"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = run_path(str(root / "src/mac_converter/__init__.py"))["__version__"]
    commit = os.environ["RELEASE_COMMIT"]
    assets = checked_assets(args.directory, version, commit)
    tag = f"v{version}"
    existing = json.loads(
        subprocess.run(
            ["gh", "api", f"repos/{os.environ['GH_REPO']}/git/matching-refs/tags/{tag}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    if any(ref["ref"] == f"refs/tags/{tag}" for ref in existing):
        raise ValueError("Release tag already exists; use a new version")
    # No --clobber or tag replacement: an existing published version stays immutable.
    subprocess.run(
        [
            "gh",
            "release",
            "create",
            tag,
            "--target",
            commit,
            "--title",
            f"Network Tools {version}",
            "--notes-file",
            str(root / "docs/RELEASE_1_1_0.md"),
            "--latest",
            *map(str, assets),
        ],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
